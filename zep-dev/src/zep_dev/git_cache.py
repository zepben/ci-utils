"""Managed Git history for resolving Distribution source locators."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import click

from zep_dev.distribution import ComponentName

REPOSITORIES: dict[ComponentName, str] = {
    "ewb": "energy-workbench-server",
    "eas": "evolve-app-server",
    "hcs": "hosting-capacity-service",
    "eas-web-client": "evolve-web-app",
}
_SHA = re.compile(r"[0-9a-f]{40}\Z")


class GitCache:
    """Own the local clones and the Git operations used for source resolution."""

    def __init__(self, root: Path | None = None) -> None:
        base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
        self.root = root if root is not None else base / "zep-dev" / "git"

    @staticmethod
    def _git(*args: str, cwd: Path | None = None, timeout: int = 300) -> str:
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
    def _remote(repo_name: str) -> str:
        return f"git@github.com:zepben/{repo_name}.git"

    def ensure_repo(self, name: ComponentName) -> Path:
        repo_name = REPOSITORIES[name]
        path = self.root / repo_name
        remote = self._remote(repo_name)
        self.root.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError(f"Git cache at {path} is a symlink; remove it and retry")
        if not path.exists():
            click.echo(f"  cloning {repo_name} into Git cache")
            temporary = Path(tempfile.mkdtemp(prefix=f".{repo_name}-", dir=self.root))
            try:
                self._git("clone", "--no-checkout", remote, str(temporary / "repo"))
                (temporary / "repo").rename(path)
            finally:
                shutil.rmtree(temporary)
        try:
            actual = self._git("remote", "get-url", "origin", cwd=path)
        except RuntimeError as exc:
            raise ValueError(
                f"Invalid Git cache at {path}; remove it and retry"
            ) from exc
        if actual != remote:
            raise ValueError(
                f"Git cache at {path} has unexpected origin; remove it and retry"
            )
        click.echo(f"  fetching {repo_name} branches and tags")
        self._git("fetch", "--prune", "--prune-tags", "origin", cwd=path)
        return path

    def _commit(self, repo: Path, ref: str) -> str:
        sha = self._git("rev-parse", "--verify", f"{ref}^{{commit}}", cwd=repo)
        if not _SHA.fullmatch(sha):
            raise RuntimeError(f"Git returned an invalid SHA for {ref}")
        return sha

    def pr_head_commit(self, repo: Path, number: int, expected_sha: str) -> str:
        self._git("fetch", "origin", f"refs/pull/{number}/head", cwd=repo)
        sha = self._commit(repo, "FETCH_HEAD")
        if sha != expected_sha:
            raise RuntimeError(
                f"PR #{number} moved from {expected_sha} to {sha}; "
                "retry distribution build"
            )
        return sha

    def trusted_commit(self, repo: Path, sha: str) -> str:
        self._git("fetch", "origin", sha, cwd=repo)
        commit = self._commit(repo, sha)
        refs = self._git(
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
        output = self._git("ls-remote", "--symref", "origin", "HEAD", cwd=repo)
        for line in output.splitlines():
            if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
                return line.removeprefix("ref: refs/heads/").removesuffix("\tHEAD")
        raise RuntimeError("Could not determine repository default branch")
