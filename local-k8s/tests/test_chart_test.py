from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

import pytest
from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute
from local_k8s.cli import cli
from local_k8s.commands.chart import test as test_module


def _write_chart(
    helm_dir: Path, chart_dir_name: str, chart_type: str | None = None
) -> Path:
    chart_yaml: dict[str, object] = {"name": chart_dir_name, "version": "1.0.0"}
    if chart_type is not None:
        chart_yaml["type"] = chart_type
    return write_chart(helm_dir / "charts" / chart_dir_name, chart_yaml)


@pytest.fixture
def patched_image_secret(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    auth_json = tmp_path / "auth.json"
    auth_json.write_text("{}\n")
    monkeypatch.setattr(test_module, "IMAGE_SECRET_PATHS", [auth_json])


def _install_chart_execute(
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> FakeExecute:
    return (
        fake_execute(test_module)
        .on("kubectl", "get", "namespaces", stdout="test-ns\n")
        .on("kubectl", "get", "secrets")
        .on("kubectl", "create", "secret")
    )


def test_test_missing_ct_yaml_fails(tmp_path: Path) -> None:
    helm_dir = tmp_path / "helm"
    helm_dir.mkdir()
    chart_dir = _write_chart(helm_dir, "mychart")

    result = CliRunner().invoke(
        cli,
        ["chart", "test", "--helm-dir", str(helm_dir), "--chart", str(chart_dir)],
    )

    assert result.exit_code != 0
    assert "ct.yaml" in result.output


def test_library_chart_skips_install(
    helm_dir: Path,
    patched_image_secret: None,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    chart_dir = _write_chart(helm_dir, "mylib", chart_type="library")
    fake = _install_chart_execute(fake_execute)

    result = CliRunner().invoke(
        cli, ["chart", "test", "--helm-dir", str(helm_dir), "--chart", str(chart_dir)]
    )

    assert result.exit_code == 0, result.output
    assert "Skipping install" in result.output
    assert fake.calls_for("ct") == []


def test_application_chart_runs_lint_and_install(
    tmp_path: Path,
    helm_dir: Path,
    patched_image_secret: None,
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_chart(helm_dir, "myapp")
    fake = _install_chart_execute(fake_execute)
    fake.on("ct", "lint-and-install")

    # Mirrors the real workflow contract: invoked from repo root with the
    # repo-root-relative path that `chart list-changed` would emit.
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        ["chart", "test", "--helm-dir", "helm", "--chart", "helm/charts/myapp"],
    )

    assert result.exit_code == 0, result.output
    assert fake.calls_for("ct")[-1] == call(
        "ct",
        "lint-and-install",
        "--config",
        "ct.yaml",
        "--charts",
        "charts/myapp",
        "--check-version-increment=true",
    )


def test_application_chart_lint_and_install_failure_raises(
    helm_dir: Path,
    patched_image_secret: None,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    chart_dir = _write_chart(helm_dir, "myapp")
    fake = _install_chart_execute(fake_execute)
    fake.on("ct", "lint-and-install", returncode=3)

    result = CliRunner().invoke(
        cli, ["chart", "test", "--helm-dir", str(helm_dir), "--chart", str(chart_dir)]
    )

    assert result.exit_code != 0
    assert "rc=3" in result.output


def test_chart_outside_helm_dir_fails(
    tmp_path: Path,
    helm_dir: Path,
    patched_image_secret: None,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    outside_chart = _write_chart(tmp_path / "other", "myapp")

    result = CliRunner().invoke(
        cli,
        ["chart", "test", "--helm-dir", str(helm_dir), "--chart", str(outside_chart)],
    )

    assert result.exit_code != 0
    assert "not inside --helm-dir" in result.output


def test_discovery_mode_processes_all_charts_and_skips_libraries(
    helm_dir: Path,
    patched_image_secret: None,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    _write_chart(helm_dir, "app-a")
    _write_chart(helm_dir, "app-b")
    _write_chart(helm_dir, "lib-a", chart_type="library")
    fake = _install_chart_execute(fake_execute)
    fake.on("ct", "lint-and-install")

    result = CliRunner().invoke(cli, ["chart", "test", "--helm-dir", str(helm_dir)])

    assert result.exit_code == 0, result.output
    assert "Skipping install" in result.output

    assert len(fake.calls_for("kubectl", "get", "namespaces")) == 1, (
        "namespace/secret setup must run once, not per chart"
    )

    assert fake.calls_for("ct") == [
        call(
            "ct",
            "lint-and-install",
            "--config",
            "ct.yaml",
            "--charts",
            "charts/app-a",
            "--check-version-increment=true",
        ),
        call(
            "ct",
            "lint-and-install",
            "--config",
            "ct.yaml",
            "--charts",
            "charts/app-b",
            "--check-version-increment=true",
        ),
    ]
