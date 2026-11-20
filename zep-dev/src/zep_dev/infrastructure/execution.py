"""Execute commands with managed-tool validation and explicit process inputs."""

import logging
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from zep_dev.infrastructure.tools import resolve

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def execute(
    *args: str,
    capture_stdout: bool = False,
    capture_stderr: bool = False,
    skip_resolve: bool = False,
    check: bool = True,
    input: str | None = None,
    env: Mapping[str, str] | None = None,
    timeout: float | None = None,
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
        env=env,
        timeout=timeout,
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
