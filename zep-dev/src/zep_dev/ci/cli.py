"""Command-line entrypoints for repository CI operations."""

import click

from zep_dev.ci.news import update_news


@click.group("ci", help="Repository CI utilities")
def ci() -> None:
    pass


@ci.command("news")
@click.option("--version", required=True, help="Snapshot version just published.")
@click.option("--repository", required=True, help="GitHub repository as owner/name.")
@click.option(
    "--dry-run",
    is_flag=True,
)
def news(version: str, repository: str, dry_run: bool) -> None:
    """Add public pull request notes to NEWS before the snapshot-bump commit."""
    result = update_news(version, repository, dry_run=dry_run)
    if result is None:
        click.echo("No NEWS.md in this repository: news is off.")
        return
    if dry_run:
        click.echo(result.content, nl=False)
    click.echo(result.summary, err=dry_run)
