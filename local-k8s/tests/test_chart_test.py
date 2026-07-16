from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import MagicMock, call

import pytest
import yaml
from click.testing import CliRunner

from local_k8s.cli import cli
from local_k8s.commands.chart import test as test_module
from local_k8s.shared import CommandResult

# Standard execute() side effects for the namespace/secret setup that runs once
# per `chart test` invocation, before any chart-specific work happens.
SETUP_RESULTS = [
    CommandResult(0, "test-ns\n", ""),  # kubectl get namespaces
    CommandResult(0, "", ""),  # kubectl get secrets (image pull secret check)
    CommandResult(0, "", ""),  # kubectl create secret (image pull secret)
]


def _write_chart(
    helm_dir: Path, chart_dir_name: str, chart_type: str | None = None
) -> Path:
    chart_dir = helm_dir / "charts" / chart_dir_name
    chart_dir.mkdir(parents=True)
    chart_yaml: dict[str, str] = {"name": chart_dir_name, "version": "1.0.0"}
    if chart_type is not None:
        chart_yaml["type"] = chart_type
    (chart_dir / "Chart.yaml").write_text(yaml.dump(chart_yaml))
    return chart_dir


@pytest.fixture
def helm_dir(tmp_path: Path) -> Path:
    d = tmp_path / "helm"
    d.mkdir()
    (d / "ct.yaml").write_text("namespace: test-ns\n")
    return d


@pytest.fixture
def patched_image_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_json = tmp_path / "auth.json"
    auth_json.write_text("{}\n")
    monkeypatch.setattr(test_module, "IMAGE_SECRET_PATHS", [auth_json])


@pytest.fixture
def mock_execute(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    mock = MagicMock()
    monkeypatch.setattr(test_module, "execute", mock)
    return mock


def test_library_chart_skips_install(
    helm_dir: Path, patched_image_secret: None, mock_execute: MagicMock
) -> None:
    _write_chart(helm_dir, "mylib", chart_type="library")
    mock_execute.side_effect = list(SETUP_RESULTS)

    result = CliRunner().invoke(
        cli, ["chart", "test", "--helm-dir", str(helm_dir), "--chart", "charts/mylib"]
    )

    assert result.exit_code == 0, result.output
    assert "Skipping install" in result.output
    assert not any(c.args[0] == "ct" for c in mock_execute.call_args_list)


def test_application_chart_runs_lint_and_install(
    helm_dir: Path, patched_image_secret: None, mock_execute: MagicMock
) -> None:
    _write_chart(helm_dir, "myapp")
    mock_execute.side_effect = [*SETUP_RESULTS, CommandResult(0, "", "")]

    result = CliRunner().invoke(
        cli, ["chart", "test", "--helm-dir", str(helm_dir), "--chart", "charts/myapp"]
    )

    assert result.exit_code == 0, result.output
    assert mock_execute.call_args_list[-1] == call(
        "ct",
        "lint-and-install",
        "--config",
        "ct.yaml",
        "--charts",
        "charts/myapp",
        "--check-version-increment=false",
    )


def test_application_chart_lint_and_install_failure_raises(
    helm_dir: Path, patched_image_secret: None, mock_execute: MagicMock
) -> None:
    _write_chart(helm_dir, "myapp")
    mock_execute.side_effect = [
        *SETUP_RESULTS,
        CalledProcessError(returncode=3, cmd=["ct", "lint-and-install"]),
    ]

    result = CliRunner().invoke(
        cli, ["chart", "test", "--helm-dir", str(helm_dir), "--chart", "charts/myapp"]
    )

    assert result.exit_code != 0
    assert "rc=3" in result.output


