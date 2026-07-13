import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Literal, overload

from local_k8s.static import TOOLS_BY_NAME

LOG = logging.getLogger(__name__)


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


@overload
def execute(*args: str, capture_stdout: Literal[True] = True) -> str: ...


@overload
def execute(*args: str, capture_stdout: Literal[False]) -> int: ...


def execute(*args: str, capture_stdout: bool = True) -> str | int:
    resolve(args[0])
    LOG.debug("Executing: %s", list(args))
    if capture_stdout:
        return subprocess.check_output(list(args), text=True)
    else:
        return subprocess.check_call(list(args))
