from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

import pytest
import yaml
from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute
from local_k8s.cli import cli
from local_k8s.commands.chart import lint as lint_module
from local_k8s.models import ChartTestingConfig


@pytest.fixture
def chart_testing_config() -> ChartTestingConfig:
    return ChartTestingConfig.model_validate(
        {
            "remote": "origin",
            "target-branch": "main",
            "chart-dirs": ["charts"],
            "chart-repos": ["example-repo=https://example.com/helm-charts"],
            "validate-maintainers": False,
            "check-version-increment": False,
            "namespace": "chart-testing",
            "release-label": "app.kubernetes.io/instance",
            "additional-commands": [],
        }
    )


@pytest.fixture
def write_chart_testing_config(
    helm_dir: Path,
) -> Callable[[ChartTestingConfig], None]:
    def write(config: ChartTestingConfig) -> None:
        (helm_dir / "ct.yaml").write_text(
            yaml.safe_dump(
                config.model_dump(by_alias=True, mode="json"), sort_keys=False
            )
        )

    return write


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
    fake = fake_execute(lint_module).on("ct", "lint")

    monkeypatch.chdir(helm_dir)
    result = CliRunner().invoke(
        cli,
        ["chart", "lint", "--helm-dir", ".", "--chart", "charts/example-chart"],
    )

    assert result.exit_code == 0
    assert fake.calls_for("ct") == [
        call(
            "ct",
            "lint",
            "--config",
            "ct.yaml",
            "--charts",
            "charts/example-chart",
            "--check-version-increment=true",
        )
    ]


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
    fake = fake_execute(lint_module).on("ct", "lint")

    monkeypatch.chdir(helm_dir)
    result = CliRunner().invoke(
        cli,
        ["chart", "lint", "--helm-dir", ".", "--chart", "charts/example-chart"],
    )

    assert result.exit_code != 0
    assert "https://example.com/helm-charts not found" in result.output
    assert "ct.yaml" in result.output
    assert fake.calls_for("ct") == []
