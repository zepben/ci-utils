"""Validate and apply application manifest files."""

from collections.abc import Sequence
from pathlib import Path

import yaml

from zep_dev.development_environments.documents import (
    UniqueKeyLoader,
    resolve_relative,
)
from zep_dev.development_environments.kubernetes import (
    KubernetesObject,
    ResourceMetadata,
    kubectl,
)
from zep_dev.development_environments.target import ExecutionTarget
from zep_dev.development_environments.templates import EnvironmentTemplate
from zep_dev.infrastructure.serialization import string_mapping


def object_headers(document: object, source: Path) -> list[KubernetesObject]:
    """Extract headers for preflight; apply uses the original, complete documents."""
    if not isinstance(document, dict):
        raise ValueError(f"{source}: manifest must be a Kubernetes object")
    fields = string_mapping(document, str(source))
    kind = fields.get("kind")
    if not isinstance(kind, str):
        raise ValueError(f"{source}: manifest must be a Kubernetes object")
    if kind == "List" or kind.endswith("List") and "items" in fields:
        items = fields.get("items")
        if not isinstance(items, list):
            raise ValueError(f"{source}: resource list items must be a list")
        return [item for entry in items for item in object_headers(entry, source)]
    api_version = fields.get("apiVersion")
    if not isinstance(api_version, str):
        raise ValueError(f"{source}: manifest requires apiVersion")
    raw_metadata = fields.get("metadata")
    if not isinstance(raw_metadata, dict):
        raise ValueError(f"{source}: manifest requires metadata.name")
    metadata = string_mapping(raw_metadata, f"{source}: metadata")
    name = metadata.get("name")
    if not isinstance(name, str):
        raise ValueError(f"{source}: manifest requires metadata.name")
    header: ResourceMetadata = {"name": name}
    namespace = metadata.get("namespace")
    if namespace is not None:
        if not isinstance(namespace, str):
            raise ValueError(f"{source}: manifest metadata.namespace must be a string")
        header["namespace"] = namespace
    return [{"apiVersion": api_version, "kind": kind, "metadata": header}]


def resolve_application_manifests(
    template_path: Path, template: EnvironmentTemplate, namespace: str
) -> tuple[Path, ...]:
    paths = tuple(
        resolve_relative(template_path, reference)
        for application in template.applications.values()
        for reference in application.manifests
    )
    for path in paths:
        validate_application_manifest(path, namespace)
    return paths


def validate_application_manifest(path: Path, namespace: str) -> None:
    with path.open(encoding="utf-8") as source:
        try:
            entries = [
                item
                for document in yaml.load_all(source, Loader=UniqueKeyLoader)
                if document is not None
                for item in object_headers(document, path)
            ]
        except yaml.YAMLError as exc:
            raise ValueError(f"{path}: invalid YAML: {exc}") from exc
    if not entries:
        raise ValueError(f"{path}: application manifest file is empty")
    for item in entries:
        explicit = item["metadata"].get("namespace")
        if explicit is not None and explicit != namespace:
            raise ValueError(
                f"{path}: {item['kind']}/{item['metadata']['name']} namespace "
                f"{explicit!r} differs from Environment namespace {namespace!r}"
            )


def apply_application_manifests(target: ExecutionTarget, paths: Sequence[Path]) -> None:
    for path in paths:
        kubectl(target, "apply", f"--namespace={target.namespace}", "-f", str(path))
