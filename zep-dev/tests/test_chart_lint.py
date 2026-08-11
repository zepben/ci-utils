from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

import pytest
from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute
from zep_dev.cli import cli
from zep_dev.commands.chart import lint as lint_module
from zep_dev.commands.chart import utils as ct_module
from zep_dev.models import ChartTestingConfig


@pytest.fixture
def dependent_chart(helm_dir: Path) -> Path:
    return write_chart(
        helm_dir / "charts" / "example-chart",
        {
            "apiVersion": "v2",
            "name": "example-chart",
            "version": "0.2.0",
            "dependencies": [
                {
                    "name": "example-dependency",
                    "version": "1.10.0",
                    "repository": "https://example.com/helm-charts",
                }
            ],
        },
    )


def test_lint_dependency_repository_present_runs_ct(
    helm_dir: Path,
    chart_testing_config: ChartTestingConfig,
    dependent_chart: Path,
    write_chart_testing_config: Callable[[ChartTestingConfig], None],
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_chart_testing_config(chart_testing_config)
    fake = (
        fake_execute(lint_module)
        .on("ct", "lint")
        .on("helm", "template")
        .on("kubeconform")
    )
    monkeypatch.setattr(ct_module, "execute", fake)

    monkeypatch.chdir(helm_dir)
    result = CliRunner().invoke(
        cli,
        ["chart", "lint", "--helm-dir", ".", "--chart", "charts/example-chart"],
    )

    assert result.exit_code == 0
    [ct_call] = fake.calls_for("ct")
    assert ct_call == call(
        "ct",
        "lint",
        "--config",
        "ct.yaml",
        "--charts",
        "charts/example-chart",
        "--check-version-increment=true",
        "--chart-yaml-schema",
        str(ct_module.files("zep_dev.resources").joinpath("chart_schema.yaml")),
        "--lint-conf",
        str(ct_module.files("zep_dev.resources").joinpath("lintconf.yaml")),
    )


def test_lint_library_chart_skips_kubeconform(
    helm_dir: Path,
    chart_testing_config: ChartTestingConfig,
    write_chart_testing_config: Callable[[ChartTestingConfig], None],
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_chart_testing_config(chart_testing_config)
    write_chart(
        helm_dir / "charts" / "common",
        {
            "apiVersion": "v2",
            "name": "common",
            "version": "0.2.0",
            "type": "library",
        },
    )
    fake = fake_execute(lint_module).on("ct", "lint")
    monkeypatch.setattr(ct_module, "execute", fake)

    monkeypatch.chdir(helm_dir)
    result = CliRunner().invoke(
        cli,
        ["chart", "lint", "--helm-dir", ".", "--chart", "charts/common"],
    )

    assert result.exit_code == 0
    assert fake.calls_for("helm", "template") == []
    assert fake.calls_for("kubeconform") == []


def test_lint_dependency_repository_missing_from_ct_config_fails(
    helm_dir: Path,
    chart_testing_config: ChartTestingConfig,
    dependent_chart: Path,
    write_chart_testing_config: Callable[[ChartTestingConfig], None],
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_testing_config.chart_repos = ["other-repo=https://other.example.com/charts"]
    write_chart_testing_config(chart_testing_config)
    fake = fake_execute(lint_module)
    monkeypatch.setattr(ct_module, "execute", fake)

    monkeypatch.chdir(helm_dir)
    result = CliRunner().invoke(
        cli,
        ["chart", "lint", "--helm-dir", ".", "--chart", "charts/example-chart"],
    )

    assert result.exit_code != 0
    assert "https://example.com/helm-charts not found" in result.output
    assert "ct.yaml" in result.output
    assert fake.calls_for("ct") == []
