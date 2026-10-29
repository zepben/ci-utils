"""Environment-targeted Kubernetes Secret creation."""

import base64
import os
from pathlib import Path

import yaml

from zep_dev.development_environments.bindings import SecretSource
from zep_dev.development_environments.distributions import GHCR_REGISTRY
from zep_dev.development_environments.kubernetes import (
    kubectl,
    resource_exists,
)
from zep_dev.development_environments.registry_config import (
    RegistryConfig,
    RegistryCredential,
)
from zep_dev.development_environments.services import OciRepository
from zep_dev.development_environments.target import (
    ExecutionTarget,
    kubernetes_name,
)
from zep_dev.errors import ZepDevError
from zep_dev.models import CiSecrets

IMAGE_SECRET_NAME = "github-registry"
IMAGE_SECRET_PATHS = (
    Path("~/.config/containers/auth.json").expanduser(),
    Path("~/.docker/config.json").expanduser(),
)


def create_env_file_secret(
    target: ExecutionTarget,
    namespace: str,
    name: str,
    content: str,
) -> None:
    namespace = kubernetes_name(namespace)
    name = kubernetes_name(name)
    if not resource_exists(target, "secret", name, namespace=namespace):
        kubectl(
            target,
            f"--namespace={namespace}",
            "create",
            "secret",
            "generic",
            name,
            "--from-env-file=/dev/stdin",
            input=content,
            sensitive=True,
        )


def create_additional_secrets(
    target: ExecutionTarget, namespace: str, ci_secrets_file: Path
) -> None:
    """Load the standalone CI Secret-file format."""
    namespace = kubernetes_name(namespace)
    config = CiSecrets.model_validate(
        yaml.safe_load(ci_secrets_file.read_text(encoding="utf-8"))
    )
    resolved = [(secret.name, secret.resolve_value()) for secret in config.secrets]
    for name, content in resolved:
        create_env_file_secret(target, namespace, name, content)


def create_bound_secret(
    target: ExecutionTarget, name: str, source: SecretSource
) -> None:
    """Resolve a validated source at use time; do not store its value in a model."""
    name = kubernetes_name(name)
    if source.env is not None:
        content = os.environ.get(source.env)
        if not content:
            raise ValueError(f"secret source for {name} is missing or empty")
    elif source.file is not None:
        content = source.file.read_text(encoding="utf-8")
    else:
        raise ValueError(f"secret source for {name} is missing")
    create_env_file_secret(target, target.namespace, name, content)


def registry_credential(registry: str) -> tuple[Path, RegistryCredential]:
    for path in IMAGE_SECRET_PATHS:
        if path.is_file():
            entry = RegistryConfig.read(path).auths.get(registry)
            if entry is not None:
                return path, entry
    raise ZepDevError(
        f"credential for {registry} was not found in local container auth"
    )


def resolve_registry_credential(registry: str) -> tuple[str, str]:
    path, entry = registry_credential(registry)
    if entry.auth is None:
        raise ValueError(f"credential for {registry} in {path} has no auth value")
    decoded = base64.b64decode(entry.auth, validate=True).decode("utf-8")
    username, password = decoded.split(":", 1)
    if not username or not password:
        raise ValueError(f"credential for {registry} in {path} is incomplete")
    return username, password


def create_image_pull_secret(target: ExecutionTarget, namespace: str) -> None:
    namespace = kubernetes_name(namespace)
    auth, _ = registry_credential(GHCR_REGISTRY)
    if not resource_exists(target, "secret", IMAGE_SECRET_NAME, namespace=namespace):
        kubectl(
            target,
            "create",
            "secret",
            "generic",
            IMAGE_SECRET_NAME,
            f"--namespace={namespace}",
            f"--from-file=.dockerconfigjson={auth}",
            "--type=kubernetes.io/dockerconfigjson",
        )


def apply_argo_oci_repository_secret(
    target: ExecutionTarget,
    namespace: str,
    repository: OciRepository,
) -> None:
    namespace = kubernetes_name(namespace)
    username, password = resolve_registry_credential(repository.registry)
    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": repository.name,
            "namespace": namespace,
            "labels": {"argocd.argoproj.io/secret-type": "repository"},
        },
        "stringData": {
            "type": "helm",
            "name": repository.name,
            "enableOCI": "true",
            "url": f"{repository.registry}/{repository.repository}",
            "username": username,
            "password": password,
        },
    }
    kubectl(target, "apply", "-f", "-", input=yaml.safe_dump(manifest), sensitive=True)
