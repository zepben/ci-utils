from importlib.resources import as_file, files
from typing import Literal

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
