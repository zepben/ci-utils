from importlib.resources import as_file, files
from pathlib import Path
from typing import Literal

from click import ClickException

from zep_dev.commands.chart.version import (
    git_describe,
    parse_git_describe,
    to_chart_version,
)
from zep_dev.models import ChartMetadata, ChartTestingConfig
from zep_dev.shared import CommandResult, execute


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
            raise ClickException(
                f"{dependency.repository} not found in {ct_path}. "
                "It needs to be added under the chart_repos list, "
                "in the format <name>=<url>"
            )


def calculate_chart_version() -> str:
    return to_chart_version(parse_git_describe(git_describe()))
