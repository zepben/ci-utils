import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from click import ClickException

from local_k8s.static import TOOLS_BY_NAME

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


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
        raise ClickException(
            f"--chart {chart} is not inside --helm-dir {helm_dir}"
        ) from e
    return ResolvedChart(
        absolute_path=absolute_path,
        path_relative_to_helm_dir=path_relative_to_helm_dir,
    )


def get_repo_name() -> str:
    if sys.prefix == sys.base_prefix:
        raise Exception("local-k8s must be run from an application virtualenv")
    return Path(sys.prefix).resolve().parent.name


def get_tools_dir() -> Path:
    repo_name = get_repo_name()
    return Path.home() / ".local" / "share" / repo_name


def get_bin_dir() -> Path:
    return get_tools_dir() / "bin"


def get_hash_dir() -> Path:
    return get_tools_dir() / "hash"


def resolve(name: str) -> None:
    """
    Ensure we have our required tools present.
    We inject the bin dir in PATH earlier in execution, but
    this acts as a runtime safeguard and prevents accidentally
    adding another tool that is not covered.
    """
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise Exception(f"Failed to locate tool: {name}")
    path = get_bin_dir() / tool.name
    if not path.is_file() or not os.access(path, os.X_OK):
        raise Exception(f"{name} not installed at {path}; run: local-k8s tools install")


def execute(
    *args: str,
    capture_stdout: bool = False,
    capture_stderr: bool = False,
    skip_resolve: bool = False,
    check: bool = True,
    input: str | None = None,
) -> CommandResult:
    if not skip_resolve:
        resolve(args[0])
    LOG.debug("Executing: %s", list(args))
    completed = subprocess.run(
        list(args),
        input=input,
        text=True,
        stdout=subprocess.PIPE if capture_stdout else None,
        stderr=subprocess.PIPE if capture_stderr else None,
        check=False,
    )
    result = CommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout or "",
        stderr=completed.stderr or "",
    )
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode,
            list(args),
            output=result.stdout,
            stderr=result.stderr,
        )
    return result
