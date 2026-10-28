"""Runtime contract reference derivation from a chart's Git history."""

from pathlib import Path

from zep_dev.chart_version import git_prefix
from zep_dev.shared import execute

RUNTIME_CONTRACT_DIRECTORY = "runtime-contract"
RUNTIME_CONTRACT_REF_ANNOTATION = "zepben.com/runtime-contract-ref"


def runtime_contract_ref(chart: Path) -> str | None:
    if not (chart / RUNTIME_CONTRACT_DIRECTORY).is_dir():
        return None
    ref = execute(
        *git_prefix(chart),
        "log",
        "-1",
        "--format=%H",
        "--",
        RUNTIME_CONTRACT_DIRECTORY,
        skip_resolve=True,
        capture_stdout=True,
    ).stdout.strip()
    if not ref:
        raise ValueError(
            f"no commit touches {chart / RUNTIME_CONTRACT_DIRECTORY}; "
            "commit the runtime contract before releasing the chart"
        )
    return ref
