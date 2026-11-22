from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from tests.support.execution import FakeExecuteFactory

from zep_dev.ci import news
from zep_dev.cli import cli
from zep_dev.errors import ZepDevError
from zep_dev.infrastructure.github_api import GitHubAPI, PullRequest

SHA = "a" * 40
OLDER = "b" * 40
MARKER = "c" * 40
VERSION = "1.2.0b4"
REPOSITORY = "zepben/commons"
PULL = PullRequest(
    number=42,
    title="Keep [the title] literal",
    html_url="https://github.com/zepben/commons/pull/42",
    body="# Upgrade notes\n\nRebuild the index.\n",
    merged_at="2026-11-18T00:00:00Z",
    merge_commit_sha=SHA,
)


@pytest.fixture
def news_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_environment: None
) -> Path:
    """Opt in within a temporary directory with isolated CLI startup, without real Git."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "NEWS.md"
    path.write_text("")
    return path


def existing_news() -> str:
    pull = PULL.model_copy(
        update={
            "number": 41,
            "title": "Previous change",
            "html_url": "https://github.com/zepben/commons/pull/41",
            "body": "# Upgrade notes\n\nOlder notes.",
        }
    )
    return news.add_version(
        "# News\n\nOur introduction.",
        "1.2.0b3",
        [news.render_entry("1.2.0b3", pull)],
    )


def invoke_news(*options: str) -> Result:
    return CliRunner().invoke(
        cli,
        ["ci", "news", "--version", VERSION, "--repository", REPOSITORY, *options],
    )


@pytest.mark.parametrize(
    ("log", "expected"),
    [
        (
            [
                (SHA, "Feature"),
                (MARKER, "Update snapshot 1 to 2 [skip ci]"),
                (OLDER, "Old"),
            ],
            [SHA],
        ),
        ([(MARKER, "Update snapshot 1 to 2 [skip ci]")], []),
        ([(SHA, "Feature"), (OLDER, "Direct push")], [SHA, OLDER]),
    ],
)
def test_news_range_stops_before_the_last_snapshot_bump(
    log: list[tuple[str, str]], expected: list[str]
) -> None:
    assert news.unwritten_commits(log) == expected


@pytest.mark.parametrize(
    ("log", "expected"),
    [
        ("", []),
        (f"{SHA}\x1fFeature\n{OLDER}\x1fEarlier feature\n", [SHA, OLDER]),
        (f"{SHA}\x1fFeature\n{MARKER}\x1fUpdate snapshot old to new\n", [SHA]),
        (f"{MARKER}\x1fUpdate snapshot old to new\n", []),
    ],
    ids=["empty-history", "no-bump", "after-bump", "bump-at-head"],
)
def test_commit_range_reads_head_once_and_stops_at_the_latest_snapshot_bump(
    fake_execute: FakeExecuteFactory, log: str, expected: list[str]
) -> None:
    range_args = (
        "git",
        "log",
        "--first-parent",
        "--max-count=101",
        "--format=%H%x1f%s",
        "HEAD",
    )
    fake = (
        fake_execute(news)
        .on("git", "rev-parse", stdout="false\n")
        .on(*range_args, stdout=log)
    )

    assert news.read_commit_range() == expected
    assert [call.args for call in fake.calls_for("git", "log")] == [range_args]


def test_exactly_one_hundred_commits_are_collected_without_truncation(
    fake_execute: FakeExecuteFactory,
) -> None:
    commits = [f"{index:040x}" for index in range(100)]
    fake_execute(news).on("git", "rev-parse", stdout="false\n").on(
        "git",
        "log",
        "--first-parent",
        stdout="".join(f"{sha}\x1fFeature\n" for sha in commits),
    )

    assert news.read_commit_range() == commits


def test_news_publishes_notes_and_nonempty_categories_not_reviewer_description() -> (
    None
):
    pull = PULL.model_copy(
        update={
            "body": """# Description
Reviewer-only discussion.

> [!NOTE]
> Upgrade notes and Change log entries are copied into NEWS.md.
> Keep the template headings; do not add headings within your notes.

# Upgrade notes
Rebuild the index.

**Example**
````markdown
# Description
Keep this code unchanged.
```
````
# Change log entries
### Breaking Changes
* None.
### Fixes
* Handle empty indexes.
### Notes
- None.
"""
        }
    )

    entry = news.render_entry(VERSION, pull)

    assert "Reviewer-only" not in entry
    assert "copied into NEWS.md" not in entry
    assert "Keep the template headings" not in entry
    assert "**Example**" in entry
    assert "````markdown\n# Description\nKeep this code unchanged.\n```\n````" in entry
    assert "##### Fixes\n\n* Handle empty indexes." in entry
    assert "Breaking Changes" not in entry
    assert "##### Notes" not in entry
    assert r"### [Keep \[the title\] literal]" in entry
    assert pull.html_url in entry
    assert news.anchor_tag(news.entry_anchor(VERSION, pull.number)) in entry


def test_publication_notice_outside_public_sections_does_not_create_an_entry() -> None:
    pull = PULL.model_copy(
        update={
            "body": """# Description
Reviewer-only discussion.

> [!NOTE]
> Upgrade notes and Change log entries are copied into NEWS.md.

# Upgrade notes
None.

# Change log entries
### Breaking Changes
* None.
### New Features
* None.
### Enhancements
* None.
### Fixes
* None.
### Notes
* None.

# Test Steps
Reviewer instructions.
"""
        }
    )

    assert news.render_entry(VERSION, pull) == ""


@pytest.mark.parametrize(
    "content",
    [
        "Restart <!-- author comment --> the service.",
        "- Run `upgrade`.\n- Read [the guide](https://example.org).\n\n"
        "```html\n<!-- retain this example -->\n# This is code, not a heading\n```",
    ],
)
def test_author_content_is_copied_without_comment_stripping(content: str) -> None:
    pull = PULL.model_copy(update={"body": f"# Upgrade notes\n\n{content}\n"})

    assert news.render_entry(VERSION, pull).endswith(f"#### Upgrade notes\n\n{content}")


@pytest.mark.parametrize(
    "body",
    [
        "# Upgrade notes\n## Extra heading\nChange the configuration.",
        "# Upgrade notes\nExtra heading\n-------------\nChange the configuration.",
        "# Change log entries\n### Fixes\n#### Extra heading\nFix the configuration.",
    ],
)
def test_extra_headings_within_public_notes_are_refused(body: str) -> None:
    pull = PULL.model_copy(update={"body": body})

    with pytest.raises(
        ValueError, match="Public notes must not contain additional headings"
    ):
        news.render_entry(VERSION, pull)


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_unclosed_root_code_fences_are_refused(fence: str) -> None:
    pull = PULL.model_copy(update={"body": f"# Upgrade notes\n{fence}text\nExample"})

    with pytest.raises(ValueError, match="unclosed code fence"):
        news.render_entry(VERSION, pull)


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_closed_root_code_fences_are_preserved(fence: str) -> None:
    content = f"{fence}text\nExample\n{fence}"
    pull = PULL.model_copy(update={"body": f"# Upgrade notes\n{content}"})

    assert news.render_entry(VERSION, pull).endswith(content)


@pytest.mark.usefixtures("cli_environment")
def test_absent_news_file_does_not_read_git_or_require_a_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_execute: FakeExecuteFactory
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    fake = fake_execute(news)

    result = invoke_news()

    assert result.exit_code == 0, result.output
    assert "news is off" in result.stdout
    assert fake.calls == []


@pytest.mark.parametrize(
    "version", ["", " ", " 1.2.0b4", "1.2.0b4 ", "1.2.0b4\t", "1.2.0\nb4"]
)
def test_invalid_versions_are_refused_before_history_reads(
    news_file: Path,
    fake_execute: FakeExecuteFactory,
    version: str,
) -> None:
    fake = fake_execute(news)

    result = CliRunner().invoke(
        cli, ["ci", "news", "--version", version, "--repository", REPOSITORY]
    )

    assert result.exit_code == 1
    assert "published version" in result.stderr
    assert news_file.read_text() == ""
    assert fake.calls == []


def test_preview_preserves_news_and_index_and_prints_only_the_proposed_file(
    news_file: Path, monkeypatch: pytest.MonkeyPatch, fake_execute: FakeExecuteFactory
) -> None:
    original = existing_news()
    news_file.write_text(original)
    fake = (
        fake_execute(news)
        .on("git", "rev-parse", stdout="false\n")
        .on(
            "git",
            "log",
            stdout=f"{SHA}\x1fFeature\n{MARKER}\x1fUpdate snapshot old to new\n",
        )
    )
    monkeypatch.setattr(GitHubAPI, "merged_pull_request", lambda self, repo, sha: PULL)

    result = invoke_news("--dry-run")

    assert result.exit_code == 0, result.output
    assert news_file.read_text() == original
    assert result.stdout.startswith("# News\n\nOur introduction.\n\n")
    assert "**Contents**" in result.stdout
    assert "## 1.2.0b4\n" in result.stdout
    assert "## 1.2.0b3\n" in result.stdout
    assert "Older notes." in result.stdout
    assert "News for 1.2.0b4" in result.stderr
    assert "News for 1.2.0b4" not in result.stdout
    assert not fake.calls_for("git", "add")
    assert not fake.calls_for("git", "fetch")
    range_call = fake.calls_for("git", "log")[0]
    assert "--first-parent" in range_call.args
    assert "HEAD" in range_call.args


@pytest.mark.parametrize("content", ["", existing_news()])
def test_existing_news_collects_the_same_range_whether_empty_or_populated(
    news_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
    content: str,
) -> None:
    news_file.write_text(content)
    fake = (
        fake_execute(news)
        .on("git", "rev-parse", stdout="false\n")
        .on(
            "git",
            "log",
            stdout=f"{SHA}\x1fFeature\n{OLDER}\x1fDirect push\n"
            f"{MARKER}\x1fUpdate snapshot old to new\n",
        )
        .on("git", "add")
    )
    looked_up: list[str] = []

    def pull_for(self: GitHubAPI, repository: str, sha: str) -> PullRequest | None:
        assert repository == REPOSITORY
        assert news_file.read_text() == content
        assert not fake.calls_for("git", "add")
        looked_up.append(sha)
        return PULL if sha == SHA else None

    monkeypatch.setattr(GitHubAPI, "merged_pull_request", pull_for)
    result = invoke_news()

    assert result.exit_code == 0, result.output
    assert looked_up == [SHA, OLDER]
    updated = news_file.read_text()
    assert f"## {VERSION}\n" in updated
    if content:
        assert "## 1.2.0b3\n" in updated
        assert "Older notes." in updated
    else:
        assert updated.startswith(news.HEADER)
    assert "**Contents**" in updated
    assert len(fake.calls_for("git", "add")) == 1
    assert fake.calls_for("git", "add")[0].args == ("git", "add", "--", "NEWS.md")
    assert "no pull request was merged" in result.stdout


def test_api_failure_leaves_news_and_the_index_unchanged(
    news_file: Path, monkeypatch: pytest.MonkeyPatch, fake_execute: FakeExecuteFactory
) -> None:
    original = "# News\n"
    news_file.write_text(original)
    fake = (
        fake_execute(news)
        .on("git", "rev-parse", stdout="false\n")
        .on("git", "log", stdout=f"{SHA}\x1fFeature\n{OLDER}\x1fSecond feature\n")
    )

    def pull_for(self: GitHubAPI, repository: str, sha: str) -> PullRequest:
        if sha == OLDER:
            raise ZepDevError("GitHub API authentication error: HTTP 403")
        return PULL

    monkeypatch.setattr(GitHubAPI, "merged_pull_request", pull_for)
    result = invoke_news()

    assert result.exit_code == 1
    assert "HTTP 403" in result.stderr
    assert news_file.read_text() == original
    assert not fake.calls_for("git", "add")


@pytest.mark.parametrize("dry_run", [False, True], ids=["write", "preview"])
@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            "# Upgrade notes\n## Extra heading\nDetails.",
            "additional headings",
        ),
        (
            """# Description
Reviewer-only discussion.

# Upgrade notes
```sh
run-example

# Change log entries
### Fixes
* None.

# Associated tasks
Reviewer-only dependencies.

# Test Steps
REVIEWER_ONLY_SENTINEL

# Checklist
- [ ] Review complete.
""",
            "unclosed code fence",
        ),
        (
            "# Upgrade notes\n<pre>\nExample\n\n# Test Steps\nREVIEWER_ONLY_SENTINEL",
            "HTML block",
        ),
    ],
    ids=[
        "headings",
        "fence-swallowing-private-sections",
        "html-swallowing-private-sections",
    ],
)
def test_invalid_public_notes_identify_the_pull_request_without_writing(
    news_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
    body: str,
    message: str,
    dry_run: bool,
) -> None:
    original = "# News\n"
    news_file.write_text(original)
    fake = (
        fake_execute(news)
        .on("git", "rev-parse", stdout="false\n")
        .on("git", "log", stdout=f"{SHA}\x1fValid notes\n{OLDER}\x1fInvalid notes\n")
    )
    invalid_pull = PULL.model_copy(
        update={
            "number": 137,
            "html_url": "https://github.com/zepben/commons/pull/137",
            "body": body,
        }
    )
    monkeypatch.setattr(
        GitHubAPI,
        "merged_pull_request",
        lambda self, repo, sha: PULL if sha == SHA else invalid_pull,
    )

    result = invoke_news("--dry-run") if dry_run else invoke_news()

    assert result.exit_code == 1
    assert message in result.stderr
    assert "Pull request #137" in result.stderr
    assert invalid_pull.html_url in result.stderr
    assert "REVIEWER_ONLY_SENTINEL" not in result.output
    assert result.stdout == ""
    assert news_file.read_text() == original
    assert not fake.calls_for("git", "add")


@pytest.mark.parametrize(
    "populated", [False, True], ids=["header-only", "with-navigation"]
)
def test_placeholder_notes_do_not_write_or_stage_an_empty_section(
    news_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
    populated: bool,
) -> None:
    original = existing_news() if populated else "# News\n"
    news_file.write_text(original)
    fake = (
        fake_execute(news)
        .on("git", "rev-parse", stdout="false\n")
        .on("git", "log", stdout=f"{SHA}\x1fFeature\n")
    )
    empty = PULL.model_copy(
        update={
            "body": "# Upgrade notes\nNone.\n# Change log entries\n### Fixes\n* None."
        }
    )
    monkeypatch.setattr(GitHubAPI, "merged_pull_request", lambda self, repo, sha: empty)

    result = invoke_news()

    assert result.exit_code == 0, result.output
    assert "0 added" in result.stdout
    assert news_file.read_text() == original
    assert not fake.calls_for("git", "add")


def test_shallow_history_is_refused_without_fetching_or_writing(
    news_file: Path, fake_execute: FakeExecuteFactory
) -> None:
    fake = fake_execute(news).on("git", "rev-parse", stdout="true\n")

    result = invoke_news("--dry-run")

    assert result.exit_code == 1
    assert "complete Git history" in result.stderr
    assert news_file.read_text() == ""
    assert len(fake.calls) == 1


@pytest.mark.parametrize("content", ["", existing_news()])
def test_exceeding_the_commit_limit_is_refused_even_when_news_is_empty(
    news_file: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
    content: str,
) -> None:
    news_file.write_text(content)
    fake = (
        fake_execute(news)
        .on("git", "rev-parse", stdout="false\n")
        .on(
            "git",
            "log",
            "--first-parent",
            stdout="".join(f"{i:040x}\x1fFeature\n" for i in range(101)),
        )
    )

    def unexpected_lookup(self: GitHubAPI, repository: str, sha: str) -> None:
        pytest.fail("an incomplete commit range must be refused before GitHub lookups")

    monkeypatch.setattr(GitHubAPI, "merged_pull_request", unexpected_lookup)
    result = invoke_news()

    assert result.exit_code == 1
    assert "more than 100" in result.stderr
    assert news_file.read_text() == content
    assert not fake.calls_for("git", "add")
