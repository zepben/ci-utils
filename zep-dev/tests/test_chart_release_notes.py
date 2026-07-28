from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

import pytest
from click import ClickException
from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute
from local_k8s.cli import cli
from local_k8s.commands.chart import release_notes as release_notes_module
from local_k8s.commands.chart.release_notes import parse_commits


@pytest.fixture
def chart_dir(helm_dir: Path) -> Path:
    return write_chart(
        helm_dir / "charts" / "example-chart",
        {"name": "example-chart", "version": "1.2.4"},
    )


def test_release_notes_without_chart_tag_outputs_initial_release(
    helm_dir: Path,
    chart_dir: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    fake = fake_execute(release_notes_module).on(
        "git",
        "-C",
        str(chart_dir),
        "describe",
        stdout=f"{'a' * 40}\n",
    )

    result = CliRunner().invoke(
        cli,
        [
            "chart",
            "release-notes",
            "--helm-dir",
            str(helm_dir),
            "--chart",
            str(chart_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == "## Changes\n\n_Initial release._\n\n"
    assert fake.calls == [
        call(
            "git",
            "-C",
            str(chart_dir),
            "describe",
            "--tags",
            "--always",
            "--abbrev=0",
            "--first-parent",
            "--match",
            "example-chart/*",
            "--candidates=9999",
            "HEAD",
            skip_resolve=True,
            capture_stdout=True,
            capture_stderr=False,
        )
    ]


def test_release_notes_since_chart_tag_outputs_commit_list(
    helm_dir: Path,
    chart_dir: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    git_log = "\0".join(
        [
            "a" * 7,  # Short sha
            "Add readiness probe",  # Description
            "b" * 7,
            "Fix service annotations",
            "",
        ]
    )
    fake = fake_execute(release_notes_module)
    fake.on(
        "git",
        "-C",
        str(chart_dir),
        "describe",
        stdout="example-chart/1.2.3\n",
    )
    fake.on(
        "git",
        "-C",
        str(chart_dir),
        "log",
        stdout=git_log,
    )

    result = CliRunner().invoke(
        cli,
        [
            "chart",
            "release-notes",
            "--helm-dir",
            str(helm_dir),
            "--chart",
            str(chart_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert result.output == (
        "## Changes\n\n"
        "- Add readiness probe (`aaaaaaa`)\n"
        "- Fix service annotations (`bbbbbbb`)\n\n"
    )


def test_release_notes_rejects_malformed_git_log_output() -> None:
    with pytest.raises(ClickException, match="incomplete record"):
        parse_commits("a" * 7 + "\0")
