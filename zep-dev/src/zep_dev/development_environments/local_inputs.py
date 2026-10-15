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
            bindings = Bindings.model_validate(read_mapping(path))
            base = path.absolute().parent
            for paths in (bindings.mounts, bindings.repositories):
                for name, value in paths.items():
                    paths[name] = base / value
            for source in bindings.secrets.values():
                if source.file is not None:
                    source.file = base / source.file
            return bindings
        if path.exists():
            raise ValueError(f"Bindings path is not a file: {path}")
    if not required:
        return Bindings()
    searched = ", ".join(map(str, candidates))
    raise FileNotFoundError(f"Bindings not found; searched: {searched}")


def resolve_inputs(template: EnvironmentTemplate, bindings: Bindings) -> ResolvedInputs:
    mounts = {
        slot: resolve_directory(bindings.mounts.get(slot), f"bindings.mounts.{slot}")
        for slot in template.inputs.mounts
    }
    argo_names = {
        name
        for service in template.services.values()
        if isinstance(service, HelmService) and service.integration is not None
        for name in service.integration.repositories
    }
    required_repositories = argo_names.copy()
    if any(
        application.database is not None
        for application in template.applications.values()
    ):
        required_repositories.add("deployments")
    repositories = {
        name: resolve_directory(
            bindings.repositories.get(name), f"bindings.repositories.{name}"
        )
        for name in sorted(required_repositories)
    }
    argo_repositories = {name: repositories[name] for name in sorted(argo_names)}
    for name, path in argo_repositories.items():
        validate_git_checkout(name, path)
    secrets: dict[str, SecretSource] = {}
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
        argo_repositories=argo_repositories,
    )


def resolve_directory(path: Path | None, context: str) -> Path:
    if path is None or not path.is_dir():
        raise ValueError(f"{context} must name an existing directory")
    return path.resolve()


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
