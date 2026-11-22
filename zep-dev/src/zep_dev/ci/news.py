"""Public pull request notes collected since the last snapshot bump."""

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from html import escape
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote

from markdown_it import MarkdownIt
from markdown_it.token import Token

from zep_dev.errors import ZepDevError
from zep_dev.infrastructure.execution import execute
from zep_dev.infrastructure.github_api import GitHubAPI, PullRequest

NEWS_FILE = Path("NEWS.md")
NOTES_HEADING = "Upgrade notes"
CHANGELOG_HEADING = "Change log entries"
BUMP_SUBJECT = "Update snapshot "
MAX_COMMITS = 100
HEADER = (
    "# News\n\n"
    "Upgrade notes and change log entries for developers using this repository, newest first.\n"
    "CI writes this file from each merged pull request; edit the pull request description, not this file.\n"
)

# Trailing hashes otherwise disappear from version headings as closing markup.
MARKDOWN_PUNCTUATION = re.compile(r"([\\`*_\[\]<>#])")
REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+\Z")
ANCHOR_TAG = re.compile(r'<a id="([^"]+)"></a>')
MARKDOWN = MarkdownIt("commonmark")


def markdown_lines(text: str) -> list[str]:
    """Keep source offsets aligned: splitlines() also splits Unicode separators."""
    return (
        text.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\x00", "\N{REPLACEMENT CHARACTER}")
        .split("\n")
    )


@dataclass(frozen=True)
class VersionSection:
    version: str
    body: str


@dataclass(frozen=True)
class NewsResult:
    content: str
    summary: str


def unwritten_commits(log: Iterable[tuple[str, str]]) -> list[str]:
    """First-parent commits, newest first, excluding the last bump commit."""
    commits = []
    for sha, subject in log:
        if subject.startswith(BUMP_SUBJECT):
            break
        commits.append(sha)
    return commits


def read_commit_range() -> list[str]:
    """Read a bounded first-parent range, stopping before the latest snapshot bump."""
    shallow = execute(
        "git",
        "rev-parse",
        "--is-shallow-repository",
        capture_stdout=True,
        skip_resolve=True,
    ).stdout.strip()
    if shallow == "true":
        raise ZepDevError(
            "NEWS requires complete Git history; use fetch-depth: 0 in checkout "
            "or fetch the missing history before running this command"
        )
    output = execute(
        "git",
        "log",
        "--first-parent",
        f"--max-count={MAX_COMMITS + 1}",
        "--format=%H%x1f%s",
        "HEAD",
        capture_stdout=True,
        skip_resolve=True,
    ).stdout
    log = []
    for line in output.split("\n"):
        if not line:
            continue
        sha, _, subject = line.partition("\x1f")
        log.append((sha, subject))
    commits = unwritten_commits(log)
    if len(commits) > MAX_COMMITS:
        raise ZepDevError(
            f"NEWS has more than {MAX_COMMITS} first-parent commits since the last "
            "snapshot bump; refusing to publish an incomplete range"
        )
    return commits


class Heading(NamedTuple):
    """A root-level heading; line numbers are zero-based."""

    line: int
    body_line: int
    inline: Token


def heading_spans(text: str, level: int) -> Iterator[Heading]:
    """Yield root headings, ignoring headings inside code or quotes."""
    for heading, inline in pairwise(MARKDOWN.parse(text)):
        if (
            heading.type == "heading_open"
            and heading.tag == f"h{level}"
            and heading.level == 0
            and heading.map is not None
        ):
            yield Heading(heading.map[0], heading.map[1], inline)


def split_sections(text: str, level: int) -> tuple[str, list[tuple[Token, str]]]:
    """Split into the text before the first heading and (heading, body) pairs.

    Code and quoted headings are not treated as boundaries.
    """
    lines = markdown_lines(text)
    headings = list(heading_spans(text, level))
    if not headings:
        return "\n".join(lines), []

    introduction = "\n".join(lines[: headings[0].line])
    # Each body runs to the next heading; the last runs to the end of the text.
    ends = [heading.line for heading in headings[1:]] + [len(lines)]
    bodies = []
    for heading, end in zip(headings, ends, strict=True):
        body = "\n".join(lines[heading.body_line : end]).strip("\n")
        bodies.append((heading.inline, body))
    return introduction, bodies


def sections(text: str, level: int) -> dict[str, str]:
    """Merge bodies of repeated headings, keyed by inline Markdown."""
    parts_by_heading: dict[str, list[str]] = {}
    for inline, content in split_sections(text, level)[1]:
        parts_by_heading.setdefault(inline.content, []).append(content)
    return {heading: "\n\n".join(parts) for heading, parts in parts_by_heading.items()}


def is_placeholder(text: str) -> bool:
    return text.strip().rstrip(".").lower() in ("", "none", "* none", "- none")


def extract_public_notes(body: str) -> tuple[str, dict[str, str]]:
    """Select upgrade notes and populated change-log categories.

    Instructions belong outside these sections: their Markdown is published,
    not sanitised or reformatted.
    """
    pull_request_sections = sections(body, 1)
    upgrade_notes = pull_request_sections.get(NOTES_HEADING, "")
    if is_placeholder(upgrade_notes):
        upgrade_notes = ""

    change_log = pull_request_sections.get(CHANGELOG_HEADING, "")
    categories = {
        name: content
        for name, content in sections(change_log, 3).items()
        if not is_placeholder(content)
    }
    return upgrade_notes, categories


def is_marker(token: Token, marker: str) -> bool:
    """A root-level HTML block holding exactly this marker comment."""
    return (
        token.type == "html_block"
        and token.level == 0
        and token.content.strip() == marker
    )


def parse_fragment(text: str) -> list[Token]:
    """Reject content that could hide the following NEWS section.

    CommonMark permits unfinished fences and HTML blocks to consume the rest of
    a document. The probe must remain a separate root block; it is never written.
    See https://spec.commonmark.org/0.31.2/#fenced-code-blocks and
    https://spec.commonmark.org/0.31.2/#html-blocks.
    """
    boundary = "<!-- news:boundary -->"
    tokens = MARKDOWN.parse(f"{text}\n\n{boundary}")
    if not is_marker(tokens[-1], boundary):
        raise ValueError(
            "Markdown contains an unclosed code fence or HTML block; "
            "close it before publishing NEWS"
        )
    return tokens[:-1]


def render_notes(text: str) -> str:
    """Validate section boundaries without reformatting author Markdown."""
    if any(token.type == "heading_open" for token in parse_fragment(text)):
        raise ValueError(
            "Public notes must not contain additional headings; "
            "use paragraphs, lists or code blocks"
        )
    return "\n".join(markdown_lines(text)).rstrip("\n")


def render_entry(version: str, pull: PullRequest) -> str:
    """Return an empty string when the PR contributes no public notes."""
    upgrade_notes, categories = extract_public_notes(pull.body or "")
    if not upgrade_notes and not categories:
        return ""

    parts: list[str] = []
    if upgrade_notes:
        parts.extend([f"#### {NOTES_HEADING}", render_notes(upgrade_notes)])
    if categories:
        parts.append(f"#### {CHANGELOG_HEADING}")
        for name, content in categories.items():
            parts.extend([f"##### {name}", render_notes(content)])

    heading = f"### [{markdown_text(pull.title)}]({pull.html_url})"
    destination = anchor_tag(entry_anchor(version, pull.number))
    return "\n\n".join([heading, destination, *parts])


def markdown_text(text: str) -> str:
    """Keep titles such as '&amp;' literal rather than rendering them as '&'."""
    return MARKDOWN_PUNCTUATION.sub(r"\\\1", escape(text, quote=False))


def version_anchor(version: str) -> str:
    return f"news-version-{quote(version, safe='')}"


def entry_anchor(version: str, number: int) -> str:
    return f"{version_anchor(version)}-pr-{number}"


def anchor_tag(anchor: str) -> str:
    return f'<a id="{escape(anchor)}"></a>'


def local_link(label: str, anchor: str) -> str:
    # IDs retain percent signs from version encoding, so links must encode them again.
    return f"[{markdown_text(label)}](#{quote(anchor, safe='')})"


def read_navigation_prefix(text: str, kind: str) -> str:
    """Only a root-level suffix is navigation; quoted/code markers are author content."""
    tokens = MARKDOWN.parse(text)
    if not tokens or not is_marker(tokens[-1], f"<!-- news:{kind}:end -->"):
        return text.rstrip("\n")

    start = f"<!-- news:{kind}:start -->"
    for token in reversed(tokens[:-1]):
        if is_marker(token, start) and token.map is not None:
            return "\n".join(markdown_lines(text)[: token.map[0]]).rstrip("\n")
    raise ValueError(f"NEWS has an incomplete {kind} block")


def read_news(news: str) -> tuple[str, tuple[VersionSection, ...]]:
    """Read version boundaries and remove only their generated outer navigation."""
    parse_fragment(news)
    introduction, bodies = split_sections(news, 2)
    introduction = read_navigation_prefix(introduction, "contents")
    versions: list[VersionSection] = []
    for inline, body in bodies:
        version = "".join(token.content for token in inline.children or [])
        source = read_navigation_prefix(body, "navigation")
        destination = anchor_tag(version_anchor(version))
        if not source.startswith(destination):
            raise ValueError(f"NEWS {version} is missing its version anchor")
        source = source[len(destination) :].strip("\n")
        versions.append(VersionSection(version, source))
    return introduction, tuple(versions)


def entry_links(section: VersionSection) -> Iterator[tuple[str, str]]:
    """Reuse stored destinations so repeated titles and later updates keep valid links."""
    lines = markdown_lines(section.body)
    for heading in heading_spans(section.body, 3):
        children = heading.inline.children or []
        if (
            len(children) < 3
            or children[0].type != "link_open"
            or children[-1].type != "link_close"
            or any(token.type != "text" for token in children[1:-1])
        ):
            raise ValueError("NEWS entry headings must be linked pull request titles")
        title = "".join(token.content for token in children[1:-1])
        # Our heading has one blank line before its anchor; never search note bodies.
        anchor_line = heading.body_line + 1
        match = (
            ANCHOR_TAG.fullmatch(lines[anchor_line])
            if anchor_line < len(lines)
            else None
        )
        if match is None or not match[1].startswith(
            version_anchor(section.version) + "-pr-"
        ):
            raise ValueError(f"NEWS {section.version} is missing an entry anchor")
        yield title, match[1]


def render_contents(versions: tuple[VersionSection, ...]) -> str:
    lines = [
        "<!-- news:contents:start -->",
        anchor_tag("news-contents"),
        "",
        "**Contents**",
        "",
    ]
    for section in versions:
        lines.append(
            f"- {local_link(section.version, version_anchor(section.version))}"
        )
        seen: set[str] = set()
        for title, anchor in entry_links(section):
            if anchor in seen:
                raise ValueError(
                    f"NEWS {section.version} contains duplicate PR anchor {anchor}"
                )
            seen.add(anchor)
            lines.append(f"  - {local_link(title, anchor)}")
    lines.append("<!-- news:contents:end -->")
    return "\n".join(lines)


def render_version(section: VersionSection, newer: str | None) -> str:
    navigation = local_link("Contents", "news-contents")
    if newer is not None:
        navigation += " | " + local_link(
            f"Next newer version: {newer}", version_anchor(newer)
        )
    return "\n\n".join(
        [
            f"## {markdown_text(section.version)}",
            anchor_tag(version_anchor(section.version)),
            section.body,
            f"<!-- news:navigation:start -->\n{navigation}\n<!-- news:navigation:end -->",
        ]
    )


def render_news(introduction: str, versions: tuple[VersionSection, ...]) -> str:
    """Derive navigation from order without reconstructing author-written note bodies."""
    rendered: list[str] = []
    seen_versions: set[str] = set()
    for index, section in enumerate(versions):
        if section.version in seen_versions:
            raise ValueError(f"NEWS contains duplicate version {section.version}")
        seen_versions.add(section.version)
        newer = versions[index - 1].version if index else None
        rendered.append(render_version(section, newer))

    parts = [introduction, render_contents(versions), *rendered]
    return "\n\n".join(part for part in parts if part) + "\n"


def add_version(news: str, version: str, entries: list[str]) -> str:
    introduction, versions = read_news(news if news.strip() else HEADER)
    new_section = VersionSection(version, "\n\n".join(entries))
    return render_news(introduction, (new_section, *versions))


def update_news(
    version: str, repository: str, *, dry_run: bool = False
) -> NewsResult | None:
    """Prepare all content before changing the file or index.

    An absent file disables collection; no public notes leaves it unchanged.
    Commit and push stay with the bump script so NEWS and the next development
    version share a commit.
    """
    if not NEWS_FILE.is_file():
        return None
    if not version or version != version.strip() or "\n" in version or "\r" in version:
        raise ValueError(
            "The published version must be a non-empty single line "
            "without surrounding whitespace"
        )
    if not REPOSITORY.fullmatch(repository):
        raise ValueError("The repository must be owner/name")
    news = NEWS_FILE.read_text(encoding="utf-8")
    commits = read_commit_range()

    api = GitHubAPI()
    entries: list[str] = []
    skipped: list[str] = []
    for sha in commits:
        pull = api.merged_pull_request(repository, sha)
        if pull is None:
            skipped.append(f"{sha[:7]}: no pull request was merged as this commit")
            continue

        try:
            entry = render_entry(version, pull)
        except ValueError as error:
            error.add_note(f"Pull request #{pull.number}: {pull.html_url}")
            raise
        if entry:
            entries.append(entry)
        else:
            skipped.append(f"#{pull.number}: no upgrade notes or change log entries")

    updated = add_version(news, version, entries) if entries else news
    if entries and not dry_run:
        NEWS_FILE.write_text(updated, encoding="utf-8")
        execute("git", "add", "--", str(NEWS_FILE), skip_resolve=True)

    summary_lines = [
        f"News for {version}: {len(entries)} added from {len(commits)} commits."
    ]
    summary_lines.extend(f"- skipped {reason}" for reason in skipped)
    return NewsResult(updated, "\n".join(summary_lines))
