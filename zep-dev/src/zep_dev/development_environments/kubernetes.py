"""Kubernetes commands bound to one Environment execution target."""

import subprocess
from importlib.resources import as_file, files
from typing import NotRequired, TypedDict

from zep_dev.development_environments.target import (
    ExecutionTarget,
    kubernetes_environment,
)
from zep_dev.shared import CommandResult, execute


class ResourceMetadata(TypedDict):
    name: str
    namespace: NotRequired[str]
    labels: NotRequired[dict[str, str]]


class KubernetesObject(TypedDict):
    apiVersion: str
    kind: str
    metadata: ResourceMetadata
    spec: NotRequired[dict[str, object]]
    type: NotRequired[str]
    stringData: NotRequired[dict[str, str]]
    data: NotRequired[dict[str, str]]


def kubectl(
    target: ExecutionTarget,
    *args: str,
    capture_stdout: bool = False,
    input: str | None = None,
    sensitive: bool = False,
) -> CommandResult:
    result = execute(
        "kubectl",
        f"--kubeconfig={target.kubeconfig}",
        f"--context={target.context}",
        *args,
        capture_stdout=capture_stdout,
        capture_stderr=sensitive,
        check=not sensitive,
        input=input,
        env=kubernetes_environment(target),
    )
    if sensitive and result.returncode:
        raise subprocess.CalledProcessError(
            result.returncode, ["kubectl", "<sensitive input>"]
        )
    return result


def resource_exists(
    target: ExecutionTarget,
    resource: str,
    name: str,
    *,
    namespace: str | None = None,
) -> bool:
    args = ["get", resource, name, "--ignore-not-found", "--output=name"]
    if namespace is not None:
        args.append(f"--namespace={namespace}")
    return bool(kubectl(target, *args, capture_stdout=True).stdout.strip())


def ensure_namespace(target: ExecutionTarget, namespace: str) -> None:
    if not resource_exists(target, "namespace", namespace):
        kubectl(target, "create", "namespace", namespace)


def apply_builtin_storage_classes(target: ExecutionTarget) -> None:
    resources = files("zep_dev.resources")
    for name in ("storageclass-ebs-sc.yaml", "storageclass-managed-csi.yaml"):
        with as_file(resources.joinpath(name)) as path:
            kubectl(target, "apply", "-f", str(path))
