"""Resolve PR and commit locators to the exact chart version in OCI."""

from pathlib import Path

import click

from zep_dev.commands.chart.version import calculate_chart_version
from zep_dev.distribution import CommitLocator, ComponentName, PullRequestLocator
from zep_dev.git_cache import REPOSITORIES, GitCache
from zep_dev.github_api import GitHubAPI

SourceLocator = PullRequestLocator | CommitLocator


def resolve_source_chart(
    name: ComponentName, locator: SourceLocator, cache: GitCache, api: GitHubAPI
) -> tuple[Path, str, str]:
    """Return the cached repository, trusted SHA, and Git-derived chart version."""
    repo_name = REPOSITORIES[name]
    if isinstance(locator, PullRequestLocator):
        click.echo(f"  resolving {name} PR #{locator.pullRequest}")
        expected = api.pr_head(repo_name, locator.pullRequest)
        repo = cache.ensure_repo(name)
        sha = cache.pr_head_commit(repo, locator.pullRequest, expected)
    else:
        repo = cache.ensure_repo(name)
        click.echo(f"  verifying {name} commit {locator.commit}")
        sha = cache.trusted_commit(repo, locator.commit)

    version = calculate_chart_version(repo, sha)
    click.echo(f"  resolved {name}: {sha} -> {version}")
    return repo, sha, version
