from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
from click.testing import CliRunner

from local_k8s.cli import cli
from local_k8s.commands.chart import list_changed as list_changed_module
from local_k8s.shared import CommandResult


def test_list_changed_passes_repo_relative_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helm_dir = tmp_path / "helm"
    helm_dir.mkdir()
    (helm_dir / "ct.yaml").write_text("{}\n")

    mock_execute = MagicMock(
        side_effect=[
            CommandResult(0, f"{tmp_path.resolve()}\n", ""),
            CommandResult(0, "", ""),
        ]
    )
    monkeypatch.setattr(list_changed_module, "execute", mock_execute)

    result = CliRunner().invoke(
        cli, ["chart", "list-changed", "--helm-dir", str(helm_dir)]
    )

    assert result.exit_code == 0
    assert mock_execute.call_args_list == [
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
