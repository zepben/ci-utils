from pathlib import Path
from unittest.mock import MagicMock, call

import pytest
from click.testing import CliRunner

from local_k8s.cli import cli
from local_k8s.commands.chart import push as push_module
from local_k8s.shared import CommandResult


def test_push_fail_if_exists_aborts_when_chart_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chart = tmp_path / "charts" / "ewb"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("name: ewb\nversion: 1.2.3\n")

    auth = tmp_path / "auth.json"
    auth.write_text("{}\n")

    mock_execute = MagicMock(return_value=CommandResult(0, "", ""))
    monkeypatch.setattr(push_module, "execute", mock_execute)

    result = CliRunner().invoke(
        cli,
        [
            "chart",
            "push",
            "--chart",
            str(chart),
            "--registry-config",
            str(auth),
            "--oci-repo",
            "org/repo",
            "--fail-if-exists",
        ],
    )

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert mock_execute.call_args_list == [
        call(
            "helm",
            "show",
            "chart",
            "oci://ghcr.io/org/repo/ewb",
            "--version",
            "1.2.3",
            "--registry-config",
            str(auth),
            check=False,
            capture_stdout=True,
            capture_stderr=True,
        ),
    ]
