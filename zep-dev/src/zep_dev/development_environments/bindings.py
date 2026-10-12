"""Machine-local input source declarations; source values remain external."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zep_dev.development_environments.names import NonEmptyStr


class SecretSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    env: NonEmptyStr | None = None
    file: Path | None = None

    @model_validator(mode="after")
    def one_source(self) -> Self:
        if (self.env is None) == (self.file is None):
            raise ValueError("secret source must specify exactly one of env or file")
        if self.file is not None and not self.file.is_absolute():
            raise ValueError("secret source file must be absolute")
        return self


class Bindings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mounts: dict[NonEmptyStr, Path] = Field(default_factory=dict)
    repositories: dict[NonEmptyStr, Path] = Field(default_factory=dict)
    secrets: dict[NonEmptyStr, SecretSource] = Field(default_factory=dict)

    @model_validator(mode="after")
    def absolute_paths(self) -> Self:
        for group, paths in (
            ("mounts", self.mounts),
            ("repositories", self.repositories),
        ):
            for key, path in paths.items():
                if not path.is_absolute():
                    raise ValueError(f"bindings.{group}.{key} must be an absolute path")
        return self
