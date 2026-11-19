"""Repository chart discovery, chart-testing configuration and path handling."""

from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field

from zep_dev.charts.metadata import ChartMetadata
from zep_dev.infrastructure.execution import CommandResult, execute

# The files should live relative to helm dir in Application repo
CT_YAML = Path("ct.yaml")


class ChartTestingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    remote: str
    target_branch: str = Field(alias="target-branch")
    chart_dirs: list[Path] = Field(alias="chart-dirs")
    chart_repos: list[str] = Field(default_factory=list, alias="chart-repos")
    validate_maintainers: bool = Field(alias="validate-maintainers")
    check_version_increment: bool = Field(alias="check-version-increment")
    namespace: str
    release_label: str = Field(alias="release-label")
    additional_commands: list[str] = Field(
        default_factory=list, alias="additional-commands"
    )

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        chart_yaml = chart_dir / "ct.yaml"
        if not chart_yaml.is_file():
            raise ValueError(f"ct.yaml not found at {chart_yaml}")
        return cls.model_validate(yaml.safe_load(chart_yaml.read_text()))


@dataclass(frozen=True)
class ResolvedChart:
    absolute_path: Path
    path_relative_to_helm_dir: Path


def resolve_chart(helm_dir: Path, chart: Path) -> ResolvedChart:
    """
    chart list-changed emits a relative path which we need to resolve for
    other commands to accept. This ensures the CI workflow in .github can
    operate without any funny string munging.
    """
    absolute_path = chart.resolve()
    try:
        path_relative_to_helm_dir = absolute_path.relative_to(helm_dir)
    except ValueError as e:
        e.add_note(f"--chart {chart} is not inside --helm-dir {helm_dir}")
        raise
    return ResolvedChart(
        absolute_path=absolute_path,
        path_relative_to_helm_dir=path_relative_to_helm_dir,
    )


def discover_charts(helm_dir: Path) -> list[Path]:
    return sorted(
        path.parent.relative_to(helm_dir)
        for path in helm_dir.glob("charts/*/Chart.yaml")
    )


def execute_ct_lint(
    command: Literal["lint", "lint-and-install"], *args: str
) -> CommandResult:
    resources = files("zep_dev.resources")
    with (
        as_file(resources.joinpath("chart_schema.yaml")) as chart_schema,
        as_file(resources.joinpath("lintconf.yaml")) as lint_config,
    ):
        return execute(
            "ct",
            command,
            *args,
            "--chart-yaml-schema",
            str(chart_schema),
            "--lint-conf",
            str(lint_config),
        )


def validate_dependencies_present(
    chart_metadata: ChartMetadata,
    ct_config: ChartTestingConfig,
    ct_path: Path,
) -> None:
    chart_repos = [repo.split("=")[-1] for repo in ct_config.chart_repos]
    for dependency in chart_metadata.dependencies:
        if dependency.repository.startswith(("oci://ghcr.io", "file://")):
            continue
        if dependency.repository not in chart_repos:
            raise ValueError(
                f"{dependency.repository} not found in {ct_path}. "
                "It needs to be added under the chart_repos list, "
                "in the format <name>=<url>"
            )
