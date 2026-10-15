"""Resolve application manifest files and delegate validation to kubectl."""

from collections.abc import Sequence
from pathlib import Path

from zep_dev.development_environments.documents import resolve_relative
from zep_dev.development_environments.kubernetes import kubectl
from zep_dev.development_environments.target import ExecutionTarget
from zep_dev.development_environments.templates import EnvironmentTemplate


def resolve_application_manifests(
    template_path: Path, template: EnvironmentTemplate
) -> tuple[Path, ...]:
    paths = tuple(
        resolve_relative(template_path, reference)
        for application in template.applications.values()
        for reference in application.manifests
    )
    for path in paths:
        with path.open("rb") as source:
            source.read(1)
    return paths


def apply_application_manifests(target: ExecutionTarget, paths: Sequence[Path]) -> None:
    for path in paths:
        kubectl(target, "apply", f"--namespace={target.namespace}", "-f", str(path))
