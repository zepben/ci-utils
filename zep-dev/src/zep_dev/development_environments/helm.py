"""Helm commands and parallel application installs for one Environment."""

import os
import signal
import subprocess
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic

import yaml
from pydantic import BaseModel, ConfigDict, TypeAdapter

from zep_dev.development_environments.chart_sources import ChartRef
from zep_dev.development_environments.distributions import APP_HELM_TIMEOUT
from zep_dev.development_environments.local_charts import LocalChartRef
from zep_dev.development_environments.services import HelmService
from zep_dev.development_environments.target import (
    ExecutionTarget,
    kubernetes_environment,
)
from zep_dev.shared import CommandResult, execute, resolve

_HELM_TERMINATION_GRACE_SECONDS = 2.0


class _Release(BaseModel):
    model_config = ConfigDict(strict=True)
    namespace: str
    name: str
    status: str


_RELEASES: TypeAdapter[list[_Release]] = TypeAdapter(list[_Release])


def helm(
    target: ExecutionTarget,
    *args: str,
    capture_stdout: bool = False,
    capture_stderr: bool = False,
    check: bool = True,
    timeout: float | None = None,
) -> CommandResult:
    return execute(
        "helm",
        *args,
        "--kubeconfig",
        str(target.kubeconfig),
        "--kube-context",
        target.context,
        capture_stdout=capture_stdout,
        capture_stderr=capture_stderr,
        check=check,
        timeout=timeout,
        env=kubernetes_environment(target),
    )


def release_statuses(target: ExecutionTarget) -> dict[tuple[str, str], str]:
    result = helm(
        target,
        "list",
        "--all-namespaces",
        "--output=json",
        capture_stdout=True,
    )
    releases = _RELEASES.validate_json(result.stdout)
    return {(item.namespace, item.name): item.status for item in releases}


def install_service(
    target: ExecutionTarget,
    name: str,
    service: HelmService,
    overlay: Mapping[str, object],
) -> None:
    namespace = service.namespace or target.namespace
    chart = service.chart
    args = [
        "install",
        name,
        chart,
        "--namespace",
        namespace,
        "--create-namespace",
        "--version",
        service.version,
        "--wait",
    ]
    if service.repository is not None:
        args.extend(["--repo", service.repository])
    with TemporaryDirectory(prefix="zep-dev-service-") as temporary_directory:
        for filename, values in (
            ("values.yaml", service.values),
            ("local-repos-overlay.yaml", overlay),
        ):
            if values:
                path = Path(temporary_directory) / filename
                path.write_text(
                    yaml.safe_dump(values, default_flow_style=False), encoding="utf-8"
                )
                args.extend(["-f", str(path)])
        helm(target, *args)


def application_install_args(
    target: ExecutionTarget,
    ref: ChartRef,
    values_path: Path | None = None,
) -> list[str]:
    args = [
        "helm",
        "upgrade",
        "--install",
        ref.name,
        ref.chart,
        "--namespace",
        target.namespace,
        "--kubeconfig",
        str(target.kubeconfig),
        "--kube-context",
        target.context,
        "--wait",
        "--rollback-on-failure",
        f"--timeout={APP_HELM_TIMEOUT}",
    ]
    if not isinstance(ref, LocalChartRef):
        args.extend(["--version", ref.version])
    if values_path is not None:
        args.extend(["-f", str(values_path)])
    return args


def stop_helm_processes(processes: Sequence[subprocess.Popen[str]]) -> None:
    """Terminate all siblings before waiting, with one shared grace period."""
    try:
        for process in processes:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
        deadline = monotonic() + _HELM_TERMINATION_GRACE_SECONDS
        for process in processes:
            with suppress(subprocess.TimeoutExpired):
                process.communicate(timeout=max(0.0, deadline - monotonic()))
    finally:
        for process in processes:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        for process in processes:
            process.communicate()


def install_applications(
    target: ExecutionTarget,
    refs: Sequence[ChartRef],
    values: Mapping[str, Mapping[str, object]],
) -> None:
    if not refs:
        return
    resolve("helm")
    with TemporaryDirectory(prefix="zep-dev-apps-") as directory:
        temporary = Path(directory)
        processes: set[subprocess.Popen[str]] = set()
        try:
            for ref in refs:
                values_path: Path | None = None
                if ref.name in values and values[ref.name]:
                    values_path = temporary / f"{ref.name}-values.yaml"
                    values_path.write_text(
                        yaml.safe_dump(values[ref.name], default_flow_style=False),
                        encoding="utf-8",
                    )
                process = subprocess.Popen(
                    application_install_args(target, ref, values_path),
                    env=kubernetes_environment(target),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding="utf-8",
                    errors="replace",
                    start_new_session=True,
                )
                processes.add(process)
            while processes:
                for process in tuple(processes):
                    try:
                        stdout, stderr = process.communicate(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        continue
                    if process.returncode:
                        raise subprocess.CalledProcessError(
                            process.returncode,
                            process.args,
                            output=stdout,
                            stderr=stderr,
                        )
                    processes.remove(process)
        finally:
            stop_helm_processes(list(processes))
