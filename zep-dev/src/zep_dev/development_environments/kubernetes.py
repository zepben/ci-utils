"""Kubernetes commands bound to one Environment execution target."""

import subprocess
from importlib.resources import as_file, files
from typing import NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zep_dev.development_environments.names import NonEmptyStr
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
    timeout: float | None = None,
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
        timeout=timeout,
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


class ServiceMetadata(BaseModel):
    model_config = ConfigDict(strict=True)

    name: NonEmptyStr
    namespace: NonEmptyStr
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class ServicePort(BaseModel):
    model_config = ConfigDict(strict=True)

    name: str = ""
    protocol: str = "TCP"
    nodePort: int | None = None


class ServiceSpec(BaseModel):
    model_config = ConfigDict(strict=True)

    type: str = "ClusterIP"
    externalTrafficPolicy: str = "Cluster"
    ports: list[ServicePort] = Field(default_factory=list)


class Service(BaseModel):
    model_config = ConfigDict(strict=True)

    metadata: ServiceMetadata
    spec: ServiceSpec


class _ServiceList(BaseModel):
    model_config = ConfigDict(strict=True)

    items: list[Service]


def observe_services(target: ExecutionTarget) -> list[Service]:
    result = kubectl(
        target,
        "get",
        "services",
        "--all-namespaces",
        "--output=json",
        "--request-timeout=10s",
        capture_stdout=True,
        timeout=15,
    )
    try:
        return _ServiceList.model_validate_json(result.stdout).items
    except ValidationError as error:
        raise ValueError("Kubernetes returned invalid Services") from error
