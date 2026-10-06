"""Machine-local paths for Profile slots.

Bindings do not change what a Distribution is.
See docs/distribution-profile-bindings.md for Distribution / Profile /
Deployment vocabulary.
"""

import os
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from zep_dev.distribution import NonEmptyStr


class Bindings(BaseModel):
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
        return self.mounts[slot]

    @classmethod
    def from_path(cls, path: Path) -> Self:
        with path.open(encoding="utf-8") as source:
            data = yaml.safe_load(source)
        if data is None:
            data = {}
        return cls.model_validate(data)


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


def load_bindings(cwd: Path | None = None) -> Bindings:
    """Use the first bindings file that exists.

    If none exists, raise FileNotFoundError with the search list.
    """
    candidates = bindings_candidates(cwd)
    for path in candidates:
        if path.is_file():
            return Bindings.from_path(path)
        if path.exists():
            raise ValueError(f"Bindings path is not a file: {path}")
    searched = ", ".join(str(path) for path in candidates)
    raise FileNotFoundError(f"Bindings not found; searched: {searched}")
