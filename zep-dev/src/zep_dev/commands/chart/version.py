import re
from dataclasses import dataclass
from subprocess import CalledProcessError

import click
from click import ClickException

from zep_dev.shared import execute

GIT_DESCRIBE_PATTERN = re.compile(
    r"^v(?P<base>\d+\.\d+\.\d+)-(?P<height>\d+)-g(?P<sha>[0-9a-f]+)$"
)


@dataclass(frozen=True, slots=True)
class GitDescribe:
    base: str
    height: int
    sha: str


def parse_git_describe(output: str) -> GitDescribe:
    match = GIT_DESCRIBE_PATTERN.fullmatch(output.strip())
    if match is None:
        raise ValueError(f"unexpected git describe output: {output.strip()!r}")

    groups = match.groupdict()
    return GitDescribe(
        base=groups["base"],
        height=int(groups["height"]),
        sha=groups["sha"],
    )


def to_chart_version(description: GitDescribe) -> str:
    if description.height == 0:
        return description.base
    return f"{description.base}-{description.height}+{description.sha}"


def git_describe() -> str:
    return execute(
        "git",
        "describe",
        # Consider lightweight and annotated tags, not only annotated.
        "--tags",
        # Always emit <tag>-<height>-g<sha>, even when HEAD is exactly on a tag
        "--long",
        # Include v-prefixed release tags, e.g. v1.37.0.
        "--match",
        "v[0-9]*.[0-9]*.[0-9]*",
        # Drop hyphen prereleases, e.g. v1.6.3-next1, v0.2.9-beta.1.
        "--exclude",
        "*-*",
        # Drop letter-suffixed builds that still match the three-part glob,
        # e.g. v2.15.0b4. Digit-then-letter avoids excluding the leading "v"
        # on normal tags like v1.37.0.
        "--exclude",
        "*[0-9][a-zA-Z]*",
        # Prefer 7-char SHAs; Git may lengthen for uniqueness.
        "--abbrev=7",
        skip_resolve=True,
        capture_stdout=True,
    ).stdout


@click.command("version")
def version() -> None:
    try:
        describe_output = parse_git_describe(git_describe())
    except CalledProcessError as e:
        raise ClickException(f"git describe failed with rc={e.returncode}") from e
    except ValueError as e:
        raise ClickException(str(e)) from e

    click.echo(to_chart_version(describe_output))
