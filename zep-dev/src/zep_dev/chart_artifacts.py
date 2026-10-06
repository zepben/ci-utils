"""Resolve Distribution chart pins and make sure they exist in the OCI store.

Apply uses resolve and check. It does not start a build.
Build uses resolve and ensure. For source pins, it can start CI and wait.
GitHub HTTP is in github_api. Git cache and OCI checks are here.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, assert_never

import click

from zep_dev import cluster
from zep_dev.commands.chart.version import calculate_chart_version
from zep_dev.distribution import (
    CHART_OCI_PREFIX,
    ChartLocator,
    ChartName,
    Charts,
    CommitLocator,
    PullRequestLocator,
    VersionLocator,
    ordered_charts,
)
from zep_dev.github_api import GitHubAPI
from zep_dev.shared import resolve_registry_config

OCI_PROBE_TIMEOUT = 60
_POLL_INTERVAL = 30
_PROGRESS_INTERVAL = 5 * 60
_TIMEOUT = 60 * 60
_SHA = re.compile(r"[0-9a-f]{40}\Z")

REPOSITORIES: dict[ChartName, str] = {
    "ewb": "energy-workbench-server",
    "eas": "evolve-app-server",
    "hcs": "hosting-capacity-service",
    "eas-web-client": "evolve-web-app",
}

type ChartSource = Literal["version", "pullRequest", "commit"]


@dataclass(frozen=True)
class ChartRef:
    name: ChartName
    version: str
    source: ChartSource
    sha: str | None = None
    repo_name: str | None = None
    repo: Path | None = None

    @property
    def chart(self) -> str:
        return f"{CHART_OCI_PREFIX}/{self.name}"

    def label(self) -> str:
        return f"{self.name}:{self.version}"


def format_chart_refs(refs: Sequence[ChartRef]) -> str:
    return ", ".join(ref.label() for ref in refs)


class GitCache:
    """Local clones used to trust PR/commit pins and derive chart versions."""

    def __init__(self, root: Path | None = None) -> None:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        self.root = root if root is not None else base / "zep-dev" / "git"

    @staticmethod
    def git(*args: str, cwd: Path | None = None, timeout: int = 300) -> str:
        result = subprocess.run(
            ["git", *args],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
            cwd=cwd,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode:
            detail = result.stderr.strip() or f"exit {result.returncode}"
            raise RuntimeError(f"git {args[0]} failed: {detail}")
        return result.stdout.strip()

    @staticmethod
    def remote(repo_name: str) -> str:
        return f"git@github.com:zepben/{repo_name}.git"

    def ensure_repo(self, name: ChartName) -> Path:
        repo_name = REPOSITORIES[name]
        path = self.root / repo_name
        remote = self.remote(repo_name)
        self.root.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError(f"Git cache at {path} is a symlink; remove it and retry")
        if not path.exists():
            click.echo(f"  cloning {repo_name} into Git cache")
            temporary = Path(tempfile.mkdtemp(prefix=f".{repo_name}-", dir=self.root))
            try:
                self.git("clone", "--no-checkout", remote, str(temporary / "repo"))
                (temporary / "repo").rename(path)
            finally:
                shutil.rmtree(temporary)
        actual = self.git("remote", "get-url", "origin", cwd=path)
        if actual != remote:
            raise ValueError(
                f"Git cache at {path} has unexpected origin; remove it and retry"
            )
        click.echo(f"  fetching {repo_name} branches and tags")
        self.git("fetch", "--prune", "--prune-tags", "origin", cwd=path)
        return path

    def commit(self, repo: Path, ref: str) -> str:
        sha = self.git("rev-parse", "--verify", f"{ref}^{{commit}}", cwd=repo)
        if not _SHA.fullmatch(sha):
            raise RuntimeError(f"Git returned an invalid SHA for {ref}")
        return sha

    def pr_head_commit(self, repo: Path, number: int, expected_sha: str) -> str:
        self.git("fetch", "origin", f"refs/pull/{number}/head", cwd=repo)
        sha = self.commit(repo, "FETCH_HEAD")
        if sha != expected_sha:
            raise RuntimeError(
                f"PR #{number} moved from {expected_sha} to {sha}; "
                "retry distribution build"
            )
        return sha

    def trusted_commit(self, repo: Path, sha: str) -> str:
        self.git("fetch", "origin", sha, cwd=repo)
        commit = self.commit(repo, sha)
        refs = self.git(
            "for-each-ref",
            "--contains",
            commit,
            "--format=%(refname)",
            "refs/remotes/origin",
            "refs/tags",
            cwd=repo,
        )
        if not refs:
            raise ValueError(
                f"Commit {sha} is not reachable from a source repository branch or tag"
            )
        return commit

    def default_branch(self, repo: Path) -> str:
        output = self.git("ls-remote", "--symref", "origin", "HEAD", cwd=repo)
        for line in output.splitlines():
            if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
                return line.removeprefix("ref: refs/heads/").removesuffix("\tHEAD")
        raise RuntimeError("Could not determine repository default branch")


def probe_oci_chart(
    name: ChartName,
    version: str,
    *,
    report: bool = True,
    timeout: float = OCI_PROBE_TIMEOUT,
) -> bool:
    """Return True if the chart is in OCI.

    Fail on errors other than not-found. Auth and network errors are not
    the same as a missing chart.
    """
    oci_ref = f"{CHART_OCI_PREFIX}/{name}"
    if report:
        click.echo(f"  checking OCI {name}:{version}")
    result = cluster.helm(
        "show",
        "chart",
        oci_ref,
        "--version",
        version,
        capture_stdout=True,
        capture_stderr=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode == 0:
        if report:
            click.echo(f"  OCI present {name}:{version}")
        return True

    detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
    message = detail.lower()
    if any(token in message for token in ("not found", "manifest unknown", "404")):
        return False
    raise RuntimeError(f"OCI error for {oci_ref}:{version}: {detail}.")


def require_ghcr_credentials() -> None:
    configured = os.environ.get("HELM_REGISTRY_CONFIG")
    path = Path(configured) if configured else resolve_registry_config()
    if path is None:
        raise FileNotFoundError(
            "GHCR credentials missing; run helm registry login ghcr.io"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    auths = data.get("auths", {})
    available = (
        "ghcr.io" in auths
        or "ghcr.io" in data.get("credHelpers", {})
        or bool(data.get("credsStore"))
    )
    if not available:
        raise FileNotFoundError(
            "GHCR credentials missing; run helm registry login ghcr.io"
        )


def wait_for_oci(ref: ChartRef) -> None:
    """Poll until the chart is in OCI, or time out with an Actions URL."""
    start = time.monotonic()
    next_progress = _PROGRESS_INTERVAL
    while True:
        if probe_oci_chart(ref.name, ref.version, report=False):
            return
        elapsed = time.monotonic() - start
        if elapsed >= next_progress:
            click.echo(f"  waiting for {ref.label()} ({int(elapsed / 60)}m elapsed)")
            next_progress = (
                int(elapsed // _PROGRESS_INTERVAL) + 1
            ) * _PROGRESS_INTERVAL
        if elapsed + _POLL_INTERVAL >= _TIMEOUT:
            raise TimeoutError(
                f"Timed out waiting for {ref.label()} from {ref.sha}; "
                f"check https://github.com/zepben/{ref.repo_name}/actions"
            )
        time.sleep(_POLL_INTERVAL)


class ChartResolver:
    def __init__(
        self,
        cache: GitCache | None = None,
        api: GitHubAPI | None = None,
    ) -> None:
        self._cache = cache
        self._api = api

    def services(self) -> tuple[GitCache, GitHubAPI]:
        if self._cache is None:
            self._cache = GitCache()
        if self._api is None:
            self._api = GitHubAPI()
        return self._cache, self._api

    def resolve(self, name: ChartName, locator: ChartLocator) -> ChartRef:
        match locator:
            case VersionLocator():
                return ChartRef(name=name, version=locator.version, source="version")
            case PullRequestLocator():
                cache, api = self.services()
                repo_name = REPOSITORIES[name]
                click.echo(f"  resolving {name} PR #{locator.pullRequest}")
                expected = api.pr_head(repo_name, locator.pullRequest)
                repo = cache.ensure_repo(name)
                sha = cache.pr_head_commit(repo, locator.pullRequest, expected)
                source: ChartSource = "pullRequest"
            case CommitLocator():
                cache, api = self.services()
                repo_name = REPOSITORIES[name]
                repo = cache.ensure_repo(name)
                click.echo(f"  verifying {name} commit {locator.commit}")
                sha = cache.trusted_commit(repo, locator.commit)
                source = "commit"
            case _:
                assert_never(locator)

        version = calculate_chart_version(repo, sha)
        click.echo(f"  resolved {name}: {sha} -> {version}")
        return ChartRef(
            name=name,
            version=version,
            source=source,
            sha=sha,
            repo_name=repo_name,
            repo=repo,
        )

    def resolve_all(self, charts: Charts) -> list[ChartRef]:
        return [self.resolve(name, locator) for name, locator in ordered_charts(charts)]

    def check(self, ref: ChartRef) -> None:
        """Require the chart in OCI. Do not start a build."""
        if probe_oci_chart(ref.name, ref.version):
            return
        match ref.source:
            case "version":
                raise FileNotFoundError(
                    f"OCI not-found for {ref.chart}:{ref.version}. "
                    "Publish this version or change the Distribution pin; "
                    "distribution build cannot build a version: locator."
                )
            case "pullRequest" | "commit":
                raise FileNotFoundError(
                    f"Missing OCI chart for charts.{ref.name}.{ref.source} "
                    f"({ref.version}); run distribution build first"
                )
            case _:
                assert_never(ref.source)

    def check_all(self, refs: list[ChartRef]) -> None:
        for ref in refs:
            self.check(ref)

    def ensure(self, ref: ChartRef) -> None:
        """Make sure the chart exists. For source pins, start CI if it is missing."""
        match ref.source:
            case "version":
                self.check(ref)
                return
            case "pullRequest" | "commit":
                pass
            case _:
                assert_never(ref.source)

        if ref.sha is None or ref.repo is None or ref.repo_name is None:
            raise ValueError(f"source ChartRef for {ref.name} is incomplete")

        if probe_oci_chart(ref.name, ref.version):
            click.echo(f"  ready {ref.label()}")
            return

        cache, api = self.services()
        require_ghcr_credentials()
        # workflow_dispatch ref is the default branch.
        # inputs.commit is the commit to build.
        workflow_ref = cache.default_branch(ref.repo)
        click.echo(
            f"  dispatching {ref.repo_name} workflow on {workflow_ref} "
            f"to build commit {ref.sha}"
        )
        api.dispatch_build(ref.repo_name, workflow_ref, ref.sha)
        click.echo(f"  waiting for {ref.label()} in OCI (up to 60m)")
        wait_for_oci(ref)
        click.echo(f"  ready {ref.label()}")
