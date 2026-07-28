from dataclasses import dataclass
from itertools import batched
from pathlib import Path
from subprocess import CalledProcessError

import click
from click import ClickException

from zep_dev.models import ChartMetadata
from zep_dev.shared import execute, resolve_chart


@dataclass(frozen=True)
class Commit:
    short_sha: str
    subject: str


def parse_commits(output: str) -> list[Commit]:
    """
    Expects the output of git log "--format=%h%x00%s". We ask git to emit the fields
    delimited by NULL entries to ensure we can cleanly split them without the chance of actual
    delimiters in the title messing everything up.
    """

    if not output:
        return []

    if not output.endswith("\0"):
        raise ClickException("git log output is missing its final NUL terminator")

    fields = output.removesuffix("\0").split("\0")

    try:
        return [
            Commit(
                short_sha=short_sha,
                subject=subject,
            )
            for short_sha, subject in batched(
                fields,
                2,
                strict=True,
            )
        ]
    except ValueError as e:
        raise ClickException("git log output contains an incomplete record") from e


def git(helm_dir: Path, *args: str) -> str:
    try:
        result = execute(
            "git",
            "-C",
            str(helm_dir),
            *args,
            skip_resolve=True,
            capture_stdout=True,
            capture_stderr=False,
        )
    except CalledProcessError as e:
        raise ClickException(f"git {args} failed with: rc={e.returncode}") from e
    return result.stdout


def previous_tag_for_chart(chart_dir: Path, chart_name: str) -> str | None:
    target = f"{chart_name}/"
    previous_tag = git(
        chart_dir,
        "describe",
        "--tags",
        # Always return an identifier, even if tag not found. This allows us to differentiate
        # between no tag found (first chart), and an error calling git for some reason.
        "--always",
        # Don't add any random crap to the end of the tag if our current commit is ahead of it
        # (as we expect it to be).
        "--abbrev=0",
        # Ensure git follows merge commit direct parent, not really an issue for us normally
        # as we squash in most repos but can't hurt.
        "--first-parent",
        # Restricts eligible tags using a glob, we only care about our charts tags.
        "--match",
        f"{target}*",
        # Look at this many tags. Overkill but harmless.
        "--candidates=9999",
        "HEAD",
    ).strip()
    # If we have a previous tag for this path, then it will be returned as eg: "ewb/0.1.0".
    # If there is no previous tag then we get a commit sha.
    if previous_tag.startswith(target):
        return previous_tag
    return None


def list_commits_since_tag(chart_dir: Path, previous_tag: str) -> list[Commit]:
    output = git(
        chart_dir,
        "log",
        "-z",
        "--first-parent",
        "--format=%h%x00%s",
        f"{previous_tag}..HEAD",
        "--",
        ".",
    )
    return parse_commits(output)


def render_release_notes(commits: list[Commit]) -> str:
    items = "\n".join(
        f"- {commit.subject} (`{commit.short_sha}`)" for commit in commits
    )
    return f"## Changes\n\n{items}\n"


@click.command("release-notes")
@click.option(
    "--helm-dir",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    required=True,
)
@click.option(
    "--chart",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    required=True,
)
def release_notes(helm_dir: Path, chart: Path) -> None:
    """Generate release notes for a chart. Must be executed before the commit is tagged in CI"""
    helm_dir = helm_dir.resolve()
    resolved_chart = resolve_chart(helm_dir, chart)
    metadata = ChartMetadata.from_chart_dir(resolved_chart.absolute_path)
    prev_tag = previous_tag_for_chart(
        chart_dir=resolved_chart.absolute_path, chart_name=metadata.name
    )
    if prev_tag is None:
        markdown = "## Changes\n\n_Initial release._\n"
    else:
        commits = list_commits_since_tag(
            chart_dir=resolved_chart.absolute_path, previous_tag=prev_tag
        )
        markdown = render_release_notes(commits)
    click.echo(markdown)
