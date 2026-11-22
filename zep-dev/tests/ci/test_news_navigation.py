from html.parser import HTMLParser
from typing import override
from urllib.parse import unquote

import pytest

from zep_dev.ci import news
from zep_dev.infrastructure.github_api import PullRequest


class NavigationLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.anchors: list[str] = []
        self.targets: list[str] = []

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        anchor = attributes.get("id")
        href = attributes.get("href")
        if anchor is not None:
            self.anchors.append(anchor)
        if href is not None and href.startswith("#"):
            self.targets.append(unquote(href[1:]))


def assert_navigation_links(document: str) -> None:
    links = NavigationLinks()
    links.feed(news.MARKDOWN.render(document))
    assert links.targets, "No local navigation links were rendered"
    assert len(links.anchors) == len(set(links.anchors)), "Duplicate anchor IDs"
    for target in links.targets:
        assert target in links.anchors, f"Missing navigation destination: {target}"


def entry(
    version: str, number: int, title: str, notes: str = "Rebuild the index."
) -> str:
    pull = PullRequest(
        number=number,
        title=title,
        html_url=f"https://github.com/zepben/commons/pull/{number}",
        body=f"# Upgrade notes\n\n{notes}",
    )
    return news.render_entry(version, pull)


def test_first_version_has_contents_with_local_title_links() -> None:
    document = news.add_version(
        "", "1.2.0b1", [entry("1.2.0b1", 42, "Handle empty indexes")]
    )

    assert document.startswith(news.HEADER)
    assert "- [1.2.0b1](#news-version-1.2.0b1)" in document
    assert "  - [Handle empty indexes](#news-version-1.2.0b1-pr-42)" in document
    assert (
        "### [Handle empty indexes](https://github.com/zepben/commons/pull/42)"
        in document
    )
    assert '<a id="news-version-1.2.0b1"></a>' in document
    assert '<a id="news-version-1.2.0b1-pr-42"></a>' in document
    assert "[#42]" not in document
    assert "[Contents](#news-contents)" in document
    assert "Next newer version" not in document
    assert [heading.content for _, _, heading in news.heading_spans(document, 2)] == [
        "1.2.0b1"
    ]


def test_versions_follow_publication_order_not_version_sort_order() -> None:
    document = news.add_version("", "2.0.0", [entry("2.0.0", 40, "First change")])
    document = news.add_version(
        document, "1.9.1", [entry("1.9.1", 41, "Second change")]
    )
    document = news.add_version(
        document,
        "2.1.0b1",
        [entry("2.1.0b1", 42, "Third change"), entry("2.1.0b1", 43, "Fourth change")],
    )

    introduction, versions = news.read_news(document)
    assert introduction == news.HEADER.rstrip("\n")
    assert [section.version for section in versions] == ["2.1.0b1", "1.9.1", "2.0.0"]
    assert "Next newer version" not in news.render_version(versions[0], None)
    assert "[Next newer version: 2.1.0b1](#news-version-2.1.0b1)" in document
    assert "[Next newer version: 1.9.1](#news-version-1.9.1)" in document
    assert all("Next newer version" not in section.body for section in versions)
    assert document.count("Next newer version") == 2
    assert_navigation_links(document)

    contents = document.split("<!-- news:contents:end -->", 1)[0]
    expected = [
        "- [2.1.0b1](#news-version-2.1.0b1)",
        "  - [Third change](#news-version-2.1.0b1-pr-42)",
        "  - [Fourth change](#news-version-2.1.0b1-pr-43)",
        "- [1.9.1](#news-version-1.9.1)",
        "  - [Second change](#news-version-1.9.1-pr-41)",
        "- [2.0.0](#news-version-2.0.0)",
        "  - [First change](#news-version-2.0.0-pr-40)",
    ]
    assert [
        line for line in contents.splitlines() if line.lstrip().startswith("- ")
    ] == expected


def test_rebuilding_navigation_is_idempotent_and_preserves_note_source() -> None:
    notes = """- Keep [the link](https://example.org).

```markdown
## Not a version
### Not a pull request
<!-- news:navigation:start -->
Example, not generated navigation.
<!-- news:navigation:end -->
```

Preserve <!-- author comment --> this paragraph.
""".rstrip("\n")
    original_entry = entry("1.2.0b1", 42, "First", notes)
    introduction = "# News\n\nOur introduction.\n\n"
    document = news.add_version(introduction, "1.2.0b1", [original_entry])
    document = news.add_version(document, "1.2.0b2", [entry("1.2.0b2", 43, "Second")])

    intro, versions = news.read_news(document)
    assert versions[1].body == original_entry
    rebuilt = news.render_news(intro, versions)
    assert rebuilt == document
    assert news.render_news(*news.read_news(rebuilt)) == document
    assert document.startswith(introduction)
    assert notes in document
    assert_navigation_links(document)
    assert document.count("<!-- news:contents:start -->") == 1
    assert document.count('<a id="news-version-1.2.0b1-pr-42"></a>') == 1
    assert document.count('<a id="news-version-1.2.0b2-pr-43"></a>') == 1
    assert len(list(news.heading_spans(document, 2))) == 2


@pytest.mark.parametrize(
    "quoted", [False, True], ids=["literal-comments", "quoted-comments"]
)
def test_navigation_markers_in_notes_are_preserved_on_first_write_and_subsequent_updates(
    quoted: bool,
) -> None:
    prefix = "> " if quoted else ""
    notes = "Keep this example:\n\n" + "\n".join(
        prefix + line
        for line in (
            "<!-- news:navigation:start -->",
            "IMPORTANT_NOTE_SENTINEL",
            "<!-- news:navigation:end -->",
        )
    )
    first_entry = entry("1.2.0b1", 42, "First", notes)
    document = news.add_version("", "1.2.0b1", [first_entry])
    assert notes in document
    assert news.read_news(document)[1][0].body == first_entry

    document = news.add_version(document, "1.2.0b2", [entry("1.2.0b2", 43, "Second")])
    assert notes in document
    assert news.read_news(document)[1][1].body == first_entry
    assert news.render_news(*news.read_news(document)) == document


def test_quoted_contents_markers_do_not_remove_the_introduction() -> None:
    introduction = """# News

> <!-- news:contents:start -->
> Keep this quoted introduction.
> <!-- news:contents:end -->"""
    document = news.add_version(
        introduction, "1.2.0b1", [entry("1.2.0b1", 42, "First")]
    )

    assert news.read_news(document)[0] == introduction
    assert document.startswith(introduction)
    assert news.render_news(*news.read_news(document)) == document


@pytest.mark.parametrize(
    "opening",
    [
        "<!-- unfinished",
        "<pre>",
        "<script>",
        "<style>",
        "<![CDATA[",
        "<?example",
        "<!DOCTYPE",
    ],
)
def test_unfinished_html_cannot_swallow_following_sections(opening: str) -> None:
    with pytest.raises(ValueError, match="unclosed code fence or HTML block"):
        entry("1.2.0b1", 42, "First", f"Example:\n\n{opening}\nLiteral content")

    with pytest.raises(ValueError, match="unclosed code fence or HTML block"):
        news.add_version(
            f"# News\n\n{opening}", "1.2.0b1", [entry("1.2.0b1", 42, "First")]
        )


@pytest.mark.parametrize(
    "notes",
    [
        "<!-- closed comment -->",
        "<pre>\n## Literal heading\n</pre>",
        "```html\n<pre>\n<!-- unfinished example\n```",
        "> ```html\n> <pre>",
    ],
)
def test_self_contained_html_and_code_are_preserved(notes: str) -> None:
    rendered_entry = entry("1.2.0b1", 42, "First", notes)
    document = news.add_version("", "1.2.0b1", [rendered_entry])

    assert notes in document
    assert news.read_news(document)[1][0].body == rendered_entry
    assert news.render_news(*news.read_news(document)) == document


def test_identical_titles_use_pr_identity_and_keep_anchors_stable() -> None:
    first = news.add_version(
        "",
        "1.2.0b1",
        [entry("1.2.0b1", 42, "Same title"), entry("1.2.0b1", 43, "Same title")],
    )
    document = news.add_version(first, "1.2.0b2", [entry("1.2.0b2", 44, "Same title")])

    for number in (42, 43):
        anchor = f"news-version-1.2.0b1-pr-{number}"
        assert f'<a id="{anchor}"></a>' in document
        assert f"[Same title](#{anchor})" in document
    assert "[Same title](#news-version-1.2.0b2-pr-44)" in document


@pytest.mark.parametrize(
    "version", ["1.2.0+build.1", "1.2.0-build.1", "version & example", "1.0 #", "#"]
)
def test_punctuation_is_escaped_and_every_local_link_has_one_destination(
    version: str,
) -> None:
    title = r"Keep [brackets] (parentheses) *literal* \\ `code` <tag> &amp;"
    document = news.add_version("", version, [entry(version, 42, title)])
    document = news.add_version(
        document, "1.3.0b1", [entry("1.3.0b1", 43, "Another title")]
    )

    assert_navigation_links(document)
    assert "Keep \\[brackets\\] (parentheses) \\*literal\\*" in document
    assert list(news.entry_links(news.read_news(document)[1][1]))[0][0] == title
    assert news.render_news(*news.read_news(document)) == document


def test_repeated_pr_numbers_in_different_versions_have_distinct_destinations() -> None:
    document = news.add_version("", "1.2.0b1", [entry("1.2.0b1", 42, "Original")])
    document = news.add_version(
        document, "1.2.0b2", [entry("1.2.0b2", 42, "Follow-up")]
    )

    assert '<a id="news-version-1.2.0b1-pr-42"></a>' in document
    assert '<a id="news-version-1.2.0b2-pr-42"></a>' in document


def test_duplicate_versions_are_refused_instead_of_producing_ambiguous_links() -> None:
    document = news.add_version("", "1.2.0b1", [entry("1.2.0b1", 42, "First")])

    with pytest.raises(ValueError, match="duplicate version"):
        news.add_version(document, "1.2.0b1", [entry("1.2.0b1", 43, "Second")])


def test_duplicate_prs_in_one_version_are_refused() -> None:
    with pytest.raises(ValueError, match="duplicate PR anchor"):
        news.add_version(
            "",
            "1.2.0b1",
            [entry("1.2.0b1", 42, "First"), entry("1.2.0b1", 42, "Second")],
        )
