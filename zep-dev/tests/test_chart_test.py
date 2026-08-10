from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from unittest.mock import call

import pytest
from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute
from zep_dev import k8s, k8s_secrets
from zep_dev.cli import cli
from zep_dev.commands.chart import test as test_module
from zep_dev.commands.chart import utils as ct_module
from zep_dev.k8s_secrets import IMAGE_SECRET_NAME


@dataclass(frozen=True)
class ChartTestFakes:
    kubectl: FakeExecute
    execute: FakeExecute


def _write_chart(
    helm_dir: Path, chart_dir_name: str, chart_type: str | None = None
) -> Path:
    chart_yaml: dict[str, object] = {"name": chart_dir_name, "version": "1.0.0"}
    if chart_type is not None:
        chart_yaml["type"] = chart_type
    return write_chart(helm_dir / "charts" / chart_dir_name, chart_yaml)


def _install_chart_fakes(
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> ChartTestFakes:
    kubectl_fake = (
        FakeExecute()
        .on("get", "namespace", "test-ns", stdout="namespace/test-ns\n")
        .on("get", "secret", IMAGE_SECRET_NAME)
        .on("create", "secret")
    )
    monkeypatch.setattr(k8s, "kubectl", kubectl_fake)
    monkeypatch.setattr(test_module, "kubectl", kubectl_fake)
    monkeypatch.setattr(k8s_secrets, "kubectl", kubectl_fake)
    return ChartTestFakes(
        kubectl=kubectl_fake,
        execute=fake_execute(ct_module),
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
    auth_json: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_dir = _write_chart(helm_dir, "mylib", chart_type="library")
    fakes = _install_chart_fakes(fake_execute, monkeypatch)

    result = CliRunner().invoke(
        cli, ["chart", "test", "--helm-dir", str(helm_dir), "--chart", str(chart_dir)]
    )

    assert result.exit_code == 0, result.output
    assert "Skipping install" in result.output
    assert fakes.execute.calls_for("ct") == []


def test_application_chart_runs_lint_and_install(
    tmp_path: Path,
    helm_dir: Path,
    auth_json: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_chart(helm_dir, "myapp")
    fakes = _install_chart_fakes(fake_execute, monkeypatch)
    fakes.execute.on("ct", "lint-and-install")

    # Mirrors the real workflow contract: invoked from repo root with the
    # repo-root-relative path that `chart list-changed` would emit.
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(
        cli,
        ["chart", "test", "--helm-dir", "helm", "--chart", "helm/charts/myapp"],
    )

    assert result.exit_code == 0, result.output
    assert fakes.execute.calls_for("ct")[-1] == call(
        "ct",
        "lint-and-install",
        "--config",
        "ct.yaml",
        "--charts",
        "charts/myapp",
        "--check-version-increment=true",
        "--chart-yaml-schema",
        str(ct_module.files("zep_dev.resources").joinpath("chart_schema.yaml")),
        "--lint-conf",
        str(ct_module.files("zep_dev.resources").joinpath("lintconf.yaml")),
    )


def test_application_chart_lint_and_install_failure_raises(
    helm_dir: Path,
    auth_json: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_dir = _write_chart(helm_dir, "myapp")
    fakes = _install_chart_fakes(fake_execute, monkeypatch)
    fakes.execute.on("ct", "lint-and-install", returncode=3)

    result = CliRunner().invoke(
        cli, ["chart", "test", "--helm-dir", str(helm_dir), "--chart", str(chart_dir)]
    )

    assert result.exit_code != 0
    assert "rc=3" in result.output


def test_chart_outside_helm_dir_fails(
    tmp_path: Path,
    helm_dir: Path,
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
    auth_json: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_chart(helm_dir, "app-a")
    _write_chart(helm_dir, "app-b")
    _write_chart(helm_dir, "lib-a", chart_type="library")
    fakes = _install_chart_fakes(fake_execute, monkeypatch)
    fakes.execute.on("ct", "lint-and-install")

    result = CliRunner().invoke(cli, ["chart", "test", "--helm-dir", str(helm_dir)])

    assert result.exit_code == 0, result.output
    assert "Skipping install" in result.output

    assert len(fakes.kubectl.calls_for("get", "namespace", "test-ns")) == 1, (
        "namespace/secret setup must run once, not per chart"
    )

    assert fakes.execute.calls_for("ct") == [
        call(
            "ct",
            "lint-and-install",
            "--config",
            "ct.yaml",
            "--charts",
            "charts/app-a",
            "--check-version-increment=true",
            "--chart-yaml-schema",
            str(ct_module.files("zep_dev.resources").joinpath("chart_schema.yaml")),
            "--lint-conf",
            str(ct_module.files("zep_dev.resources").joinpath("lintconf.yaml")),
        ),
        call(
            "ct",
            "lint-and-install",
            "--config",
            "ct.yaml",
            "--charts",
            "charts/app-b",
            "--check-version-increment=true",
            "--chart-yaml-schema",
            str(ct_module.files("zep_dev.resources").joinpath("chart_schema.yaml")),
            "--lint-conf",
            str(ct_module.files("zep_dev.resources").joinpath("lintconf.yaml")),
        ),
    ]
