from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.support.execution import FakeExecuteFactory, call
from zep_dev.cli import cli
from zep_dev.commands.chart import list_changed as list_changed_module

pytestmark = pytest.mark.usefixtures("cli_environment")


def test_list_changed_passes_repo_relative_paths(
    tmp_path: Path,
    helm_dir: Path,
    fake_execute: FakeExecuteFactory,
) -> None:
    fake = fake_execute(list_changed_module)
    fake.on("git", stdout=f"{tmp_path.resolve()}\n")
    fake.on("ct", "list-changed")

    result = CliRunner().invoke(
        cli, ["chart", "list-changed", "--helm-dir", str(helm_dir)]
    )

    assert result.exit_code == 0
    assert fake.calls_for("ct", "list-changed") == [
        call(
            "ct",
            "list-changed",
            "--config",
            "helm/ct.yaml",
            "--chart-dirs",
            "helm/charts",
            "--target-branch",
            "main",
            capture_stdout=True,
        ),
    ]
