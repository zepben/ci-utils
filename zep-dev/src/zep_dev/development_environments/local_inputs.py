"""Discover Bindings and inspect only sources required by a Template."""

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from zep_dev.development_environments.bindings import Bindings, SecretSource
from zep_dev.development_environments.documents import read_mapping
from zep_dev.development_environments.services import HelmService
from zep_dev.development_environments.templates import EnvironmentTemplate


@dataclass(frozen=True)
class ResolvedInputs:
    mounts: dict[str, Path]
    repositories: dict[str, Path]
    secrets: dict[str, SecretSource]
    argo_repositories: dict[str, Path]


def bindings_candidates(cwd: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    explicit = os.environ.get("ZEP_DEV_BINDINGS")
    if explicit:
        candidates.append(Path(explicit))
    candidates.append(
        (cwd if cwd is not None else Path.cwd()) / ".zep-dev" / "bindings.yaml"
    )
    config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(config_home) if config_home else Path.home() / ".config"
    candidates.append(base / "zep-dev" / "bindings.yaml")
    return candidates


def load_bindings(cwd: Path | None = None, *, required: bool = True) -> Bindings:
    candidates = bindings_candidates(cwd)
    for path in candidates:
        if path.is_file():
            return Bindings.model_validate(read_mapping(path))
        if path.exists():
            raise ValueError(f"Bindings path is not a file: {path}")
    if not required:
        return Bindings()
    searched = ", ".join(map(str, candidates))
    raise FileNotFoundError(f"Bindings not found; searched: {searched}")


def resolve_inputs(template: EnvironmentTemplate, bindings: Bindings) -> ResolvedInputs:
    mounts: dict[str, Path] = {}
    repositories: dict[str, Path] = {}
    secrets: dict[str, SecretSource] = {}
    for slot in template.inputs.mounts:
        path = bindings.mounts.get(slot)
        if path is None or not path.is_dir():
            raise ValueError(f"bindings.mounts.{slot} must name an existing directory")
        mounts[slot] = path.resolve()
    argo_repositories = {
        name
        for service in template.services.values()
        if isinstance(service, HelmService) and service.integration is not None
        for name in service.integration.repositories
    }
    required_repositories = argo_repositories.copy()
    if any(
        application.database is not None
        for application in template.applications.values()
    ):
        required_repositories.add("deployments")
    for name in template.inputs.repositories:
        if name not in required_repositories:
            continue
        path = bindings.repositories.get(name)
        if path is None or not path.is_dir():
            raise ValueError(
                f"bindings.repositories.{name} must name an existing directory"
            )
        repositories[name] = path.resolve()
    for name in sorted(argo_repositories):
        validate_git_checkout(name, repositories[name])
    for key in template.inputs.secrets:
        source = bindings.secrets.get(key)
        if source is None:
            raise ValueError(f"bindings.secrets.{key} is required")
        validate_secret_source(key, source)
        secrets[key] = source
    return ResolvedInputs(
        mounts=mounts,
        repositories=repositories,
        secrets=secrets,
        argo_repositories={
            name: repositories[name] for name in sorted(argo_repositories)
        },
    )


def validate_git_checkout(name: str, path: Path) -> None:
    result = subprocess.run(
        ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    toplevel = result.stdout.strip()
    if result.returncode or not toplevel or Path(toplevel).resolve() != path:
        raise ValueError(
            f"bindings.repositories.{name} must be a Git checkout top level: {path}"
        )


def validate_secret_source(key: str, source: SecretSource) -> None:
    if source.env is not None:
        if not os.environ.get(source.env):
            raise ValueError(
                f"bindings.secrets.{key} environment source is missing or empty"
            )
    elif source.file is not None:
        try:
            with source.file.open("rb") as handle:
                handle.read(1)
        except OSError as exc:
            raise ValueError(
                f"bindings.secrets.{key} file source is unreadable"
            ) from exc


def load_required_inputs(
    template: EnvironmentTemplate, cwd: Path | None = None
) -> ResolvedInputs:
    required = bool(
        template.inputs.mounts
        or template.inputs.repositories
        or template.inputs.secrets
    )
    return resolve_inputs(template, load_bindings(cwd, required=required))
