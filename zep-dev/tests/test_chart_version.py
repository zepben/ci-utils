import pytest
from click.testing import CliRunner

from _fake_execute import FakeExecuteFactory
from zep_dev.cli import cli
from zep_dev.commands.chart import version as version_module
from zep_dev.commands.chart.version import (
    GitDescribe,
    parse_git_describe,
    to_chart_version,
)


@pytest.mark.parametrize(
    ("output", "description", "chart_version"),
    [
        (
            "v1.37.0-5-gd95cc75\n",
            GitDescribe(base="1.37.0", height=5, sha="d95cc75"),
            "1.37.0-5+d95cc75",
        ),
        (
            "v2.8.0-0-g2150994abcdef\n",
            GitDescribe(base="2.8.0", height=0, sha="2150994abcdef"),
            "2.8.0",
        ),
    ],
)
def test_parse_and_transform_git_describe(
    output: str,
    description: GitDescribe,
    chart_version: str,
) -> None:
    parsed = parse_git_describe(output)

    assert parsed == description
    assert to_chart_version(parsed) == chart_version


@pytest.mark.parametrize(
    "output",
    [
        "v2.8-17-g2150994",
        "6.33.0-26-gd7cb808",
    ],
)
def test_parse_git_describe_rejects_unexpected_output(output: str) -> None:
    with pytest.raises(ValueError, match="unexpected git describe output"):
        parse_git_describe(output)


def test_version_uses_stable_release_tags(
    fake_execute: FakeExecuteFactory,
) -> None:
    fake = fake_execute(version_module)
    fake.on("git", "describe", stdout="v1.37.0-5-gd95cc75\n")

    result = CliRunner().invoke(cli, ["chart", "version"])

    assert result.exit_code == 0
    assert result.stdout == "1.37.0-5+d95cc75\n"
