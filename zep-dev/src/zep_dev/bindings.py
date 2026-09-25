"""Developer-local path bindings for Profile slots.

Bindings answer where files live on this machine. They do not change what a
Distribution is. See docs/distribution-profile-bindings.md.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Annotated, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

NonEmptyStr = Annotated[str, Field(min_length=1)]


class Bindings(BaseModel):
    """Absolute paths that satisfy Profile path slots."""

    model_config = ConfigDict(extra="forbid")

    deployments_root: Path | None = None
    mounts: dict[NonEmptyStr, Path] = Field(default_factory=dict)

    @field_validator("deployments_root")
    @classmethod
    def deployments_root_absolute(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("deployments_root must be an absolute path")
        return value

    @field_validator("mounts")
    @classmethod
    def mount_paths_absolute(cls, mounts: dict[str, Path]) -> dict[str, Path]:
        for slot, path in mounts.items():
            if not path.is_absolute():
                raise ValueError(f"mounts.{slot} must be an absolute path")
        return mounts

    def require_deployments_root(self) -> Path:
        if self.deployments_root is None:
            raise ValueError(
                "bindings.deployments_root is required when the Profile enables terraform"
            )
        return self.deployments_root

    def require_mount(self, slot: str) -> Path:
        try:
            return self.mounts[slot]
        except KeyError as exc:
            raise ValueError(f"bindings.mounts has no entry for slot {slot!r}") from exc

    @classmethod
    def from_path(cls, path: Path) -> Self:
        with path.open(encoding="utf-8") as source:
            data = yaml.safe_load(source)
        if data is None:
            data = {}
        return cls.model_validate(data)


def bindings_candidates(cwd: Path | None = None) -> list[Path]:
    """Return candidate files in discovery order."""
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


def load_bindings(cwd: Path | None = None) -> Bindings:
    """Load the first existing bindings file; list searched paths when none exists."""
    candidates = bindings_candidates(cwd)
    for path in candidates:
        if path.is_file():
            return Bindings.from_path(path)
        if path.exists():
            raise ValueError(f"Bindings path is not a file: {path}")
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Bindings not found; searched: {searched}")
