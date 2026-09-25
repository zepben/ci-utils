"""Ensure Distribution charts exist in the shared OCI store."""

import time
from pathlib import Path

import click
from tenacity import (
    RetryCallState,
    RetryError,
    Retrying,
    retry_if_result,
    stop_after_delay,
)

from zep_dev.distribution import ComponentName, Distribution, VersionLocator
from zep_dev.git_cache import REPOSITORIES, GitCache
from zep_dev.github_api import GitHubAPI
from zep_dev.oci import (
    OCI_PROBE_TIMEOUT,
    check_oci_chart,
    probe_oci_chart,
    require_ghcr_credentials,
)
from zep_dev.source_chart import SourceLocator, resolve_source_chart

_POLL_INTERVAL = 30
_PROGRESS_INTERVAL = 5 * 60
_TIMEOUT = 60 * 60


def ensure_source_chart(
    name: ComponentName, locator: SourceLocator, cache: GitCache, api: GitHubAPI
) -> None:
    repo_name = REPOSITORIES[name]
    repo, sha, version = resolve_source_chart(name, locator, cache, api)
    if probe_oci_chart(name, version):
        click.echo(f"  ready {name}:{version}")
        return

    require_ghcr_credentials()
    # workflow_dispatch ref = default branch (workflow YAML); inputs.commit = build target.
    workflow_ref = cache.default_branch(repo)
    click.echo(
        f"  dispatching {repo_name} workflow on {workflow_ref} "
        f"to build commit {sha}"
    )
    api.dispatch_build(repo_name, workflow_ref, sha)
    click.echo(f"  waiting for {name}:{version} in OCI (up to 60m)")
    deadline = time.monotonic() + _TIMEOUT
    next_progress = _PROGRESS_INTERVAL

    def report_progress(state: RetryCallState) -> None:
        nonlocal next_progress
        elapsed = state.seconds_since_start or 0
        if elapsed >= next_progress:
            click.echo(f"  waiting for {name}:{version} ({int(elapsed / 60)}m elapsed)")
            next_progress = (
                int(elapsed // _PROGRESS_INTERVAL) + 1
            ) * _PROGRESS_INTERVAL

    def probe() -> bool:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError
        present = probe_oci_chart(
            name,
            version,
            report=False,
            timeout=min(OCI_PROBE_TIMEOUT, remaining),
        )
        if time.monotonic() > deadline:
            raise TimeoutError
        return present

    def wait_for_next_probe(state: RetryCallState) -> float:
        return min(_POLL_INTERVAL, max(0, deadline - time.monotonic()))

    try:
        Retrying(
            stop=stop_after_delay(_TIMEOUT),
            wait=wait_for_next_probe,
            retry=retry_if_result(lambda present: not present),
            before_sleep=report_progress,
        )(probe)
    except (RetryError, TimeoutError) as exc:
        raise TimeoutError(
            f"Timed out waiting for {name}:{version} from {sha}; "
            f"check https://github.com/zepben/{repo_name}/actions"
        ) from exc
    click.echo(f"  ready {name}:{version}")


@click.command("build")
@click.option(
    "--distribution",
    "distribution_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to Distribution YAML.",
)
def build(distribution_path: Path) -> None:
    """Ensure every Distribution chart has an installable OCI artifact."""
    distribution = Distribution.from_path(distribution_path)

    git_cache: GitCache | None = None
    api: GitHubAPI | None = None
    for name, locator in distribution.components.iter_locators():
        click.echo(f"Processing {name}")
        if isinstance(locator, VersionLocator):
            check_oci_chart(name, locator.version)
            continue
        if git_cache is None or api is None:
            git_cache = GitCache()
            api = GitHubAPI()
        ensure_source_chart(name, locator, git_cache, api)
    click.echo("Distribution charts ready")
