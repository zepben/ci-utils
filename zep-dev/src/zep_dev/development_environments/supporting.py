"""Kubernetes operations shared by supporting service integrations."""

import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zep_dev.development_environments.cnpg import DatabaseConnection
from zep_dev.development_environments.documents import resolve_relative
from zep_dev.development_environments.kubernetes import KubernetesObject, kubectl
from zep_dev.development_environments.services import (
    ConfigMapFromFile,
    HelmService,
    RawService,
)
from zep_dev.development_environments.target import ExecutionTarget


class _Secret(BaseModel):
    model_config = ConfigDict(strict=True, hide_input_in_errors=True)
    data: dict[str, str] = Field(default_factory=dict)


def apply_raw_service(target: ExecutionTarget, service: RawService) -> None:
    for url in service.manifests:
        kubectl(target, "apply", "--server-side", "-f", url)
    kubectl(
        target,
        "wait",
        "--for=condition=Established",
        "customresourcedefinitions",
        "--all",
        f"--timeout={service.wait_timeout}",
    )


@dataclass(frozen=True)
class ResolvedConfigMap:
    name: str
    data: dict[str, str]


def resolve_config_maps(
    template_path: Path, configs: Sequence[ConfigMapFromFile]
) -> tuple[ResolvedConfigMap, ...]:
    return tuple(
        ResolvedConfigMap(
            name=config.name,
            data={
                key: resolve_relative(template_path, reference).read_text(
                    encoding="utf-8"
                )
                for key, reference in config.from_file.items()
            },
        )
        for config in configs
    )


def apply_config_maps(
    target: ExecutionTarget,
    namespace: str,
    configs: Sequence[ResolvedConfigMap],
) -> None:
    for config in configs:
        manifest: KubernetesObject = {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": config.name, "namespace": namespace},
            "data": config.data,
        }
        kubectl(target, "apply", "-f", "-", input=yaml.safe_dump(manifest))


def wait_for_resources(target: ExecutionTarget, service: HelmService) -> None:
    for wait in service.wait_for:
        namespace = wait.namespace or service.namespace or target.namespace
        kubectl(
            target,
            "wait",
            f"--for={wait.for_}",
            wait.resource,
            f"--namespace={namespace}",
            f"--timeout={wait.timeout}",
        )


def secret_data(data: dict[str, str], *keys: str) -> str:
    for key in keys:
        if key in data:
            return base64.b64decode(data[key], validate=True).decode("utf-8")
    raise ValueError(f"Secret data does not contain any of: {', '.join(keys)}")


def apply_load_db_credentials(target: ExecutionTarget, service: HelmService) -> None:
    credentials = service.load_db_credentials
    if credentials is None:
        return
    namespace = service.namespace or target.namespace
    source = kubectl(
        target,
        "get",
        "secret",
        credentials.from_secret,
        f"--namespace={namespace}",
        "--output=json",
        capture_stdout=True,
    )
    try:
        data = _Secret.model_validate_json(source.stdout).data
    except ValidationError as error:
        raise ValueError("kubectl returned invalid Secret data") from error
    config: DatabaseConnection = {
        "host": secret_data(data, "host"),
        "port": int(secret_data(data, "port")),
        "name": credentials.database,
        "username": secret_data(data, "username", "user"),
        "password": secret_data(data, "password"),
    }
    manifest: KubernetesObject = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": "ewb-load-database-config", "namespace": namespace},
        "type": "Opaque",
        "stringData": {"load-database.json": json.dumps(config, separators=(",", ":"))},
    }
    kubectl(target, "apply", "-f", "-", input=yaml.safe_dump(manifest), sensitive=True)
