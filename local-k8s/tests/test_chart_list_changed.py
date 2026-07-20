from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

from click.testing import CliRunner

from _fake_execute import FakeExecute
from local_k8s.cli import cli
from local_k8s.commands.chart import list_changed as list_changed_module


def test_list_changed_passes_repo_relative_paths(
    tmp_path: Path,
    helm_dir: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    fake = fake_execute(list_changed_module)
    fake.on("git", stdout=f"{tmp_path.resolve()}\n")
    fake.on("ct", "list-changed")

    result = CliRunner().invoke(
        cli, ["chart", "list-changed", "--helm-dir", str(helm_dir)]
    )

    assert result.exit_code == 0
    assert fake.calls == [
        call(
            "git",
            "-C",
            str(helm_dir.absolute()),
            "rev-parse",
            "--show-toplevel",
            skip_resolve=True,
            capture_stdout=True,
        ),
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
