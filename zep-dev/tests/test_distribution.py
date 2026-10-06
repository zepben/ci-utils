from io import StringIO

import pytest
from pydantic import TypeAdapter, ValidationError

from zep_dev.distribution import (
    Charts,
    CommitLocator,
    Distribution,
    PullRequestLocator,
    VersionLocator,
)

FULL_SHA = "a" * 40


def test_distribution_loads_yaml_including_eas_web_client_alias() -> None:
    distribution = Distribution.from_text_io(
        StringIO(
            """\
metadata:
  name: platform-latest
charts:
  ewb:
    version: "2.1.0"
  eas-web-client:
    version: "1.0.0"
"""
        )
    )
    assert distribution.metadata.name == "platform-latest"
    assert distribution.charts["ewb"] == VersionLocator(version="2.1.0")
    assert distribution.charts["eas-web-client"] == VersionLocator(version="1.0.0")
    assert set(distribution.charts) == {"ewb", "eas-web-client"}


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"version": "1.0.0"}, VersionLocator(version="1.0.0")),
        ({"pullRequest": 268}, PullRequestLocator(pullRequest=268)),
        ({"commit": FULL_SHA}, CommitLocator(commit=FULL_SHA)),
    ],
)
def test_locator_accepts_exactly_one_kind(
    payload: dict[str, object],
    expected: VersionLocator | PullRequestLocator | CommitLocator,
) -> None:
    assert TypeAdapter(Charts).validate_python({"ewb": payload})["ewb"] == expected


def test_locator_rejects_multiple_kinds() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TypeAdapter(Charts).validate_python(
            {"ewb": {"version": "1.0.0", "pullRequest": 1}}
        )


@pytest.mark.parametrize(
    "charts", [{}, {"unknown": {"version": "1.0.0"}}, {"ewb": None}]
)
def test_charts_reject_empty_unknown_or_null_entries(
    charts: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        TypeAdapter(Charts).validate_python(charts)
