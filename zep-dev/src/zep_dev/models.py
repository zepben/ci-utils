import os
from contextlib import suppress
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArchiveFormat(StrEnum):
    NONE = "none"
    TAR_GZ = "tar.gz"
    ZIP = "zip"


class RequiredTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    url: str
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    archive_member: str | None = None
    archive_format: ArchiveFormat = ArchiveFormat.NONE

    @model_validator(mode="after")
    def validate_archive_configuration(self) -> Self:
        has_archive = self.archive_format is not ArchiveFormat.NONE
        if has_archive != (self.archive_member is not None):
            raise ValueError("archive_member and archive_format must be set together")
        return self

    def to_hash(self) -> str:
        return f"{self.name}-{self.version}-{self.url}-{self.sha256}"

    def exists(self, hash_dir: Path) -> bool:
        with suppress(OSError):
            return (hash_dir / self.name).read_text() == self.to_hash()
        return False

    def write_hash(self, hash_dir: Path) -> None:
        (hash_dir / self.name).write_text(self.to_hash())


class ChartTestingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    remote: str
    target_branch: str = Field(alias="target-branch")
    chart_dirs: list[Path] = Field(alias="chart-dirs")
    chart_repos: list[str] = Field(default_factory=list, alias="chart-repos")
    validate_maintainers: bool = Field(alias="validate-maintainers")
    check_version_increment: bool = Field(alias="check-version-increment")
    namespace: str
    release_label: str = Field(alias="release-label")
    additional_commands: list[str] = Field(
        default_factory=list, alias="additional-commands"
    )

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        chart_yaml = chart_dir / "ct.yaml"
        if not chart_yaml.is_file():
            raise ValueError(f"ct.yaml not found at {chart_yaml}")
        return cls.model_validate(yaml.safe_load(chart_yaml.read_text()))


class CiSecret(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    env_var: str = Field(min_length=1)

    def resolve_value(self) -> str:
        value = os.environ.get(self.env_var)
        if value is None or value == "":
            raise ValueError(f"{self.env_var} is not set")
        return value


class CiSecrets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secrets: list[CiSecret]


class ChartDependency(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    repository: str = Field(min_length=1)


class ChartMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    type: str = "application"
    appVersion: str | None = None
    annotations: dict[str, str] = Field(default_factory=dict)
    dependencies: list[ChartDependency] = Field(default_factory=list)

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        chart_yaml = chart_dir / "Chart.yaml"
        if not chart_yaml.is_file():
            raise ValueError(f"Chart.yaml not found at {chart_yaml}")
        return cls.model_validate(yaml.safe_load(chart_yaml.read_text()))

    def write(self, chart_dir: Path) -> None:
        (chart_dir / "Chart.yaml").write_text(
            yaml.safe_dump(
                self.model_dump(mode="json", exclude_unset=True),
                sort_keys=False,
            )
        )


class ChartImageValues(BaseModel):
    model_config = ConfigDict(extra="allow")

    tag: str | None = None


class ChartValues(BaseModel):
    model_config = ConfigDict(extra="allow")

    image: ChartImageValues = Field(default_factory=ChartImageValues)

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        values_yaml = chart_dir / "values.yaml"
        if not values_yaml.is_file():
            return cls()
        return cls.model_validate(yaml.safe_load(values_yaml.read_text()))

    def write(self, chart_dir: Path) -> None:
        (chart_dir / "values.yaml").write_text(
            yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)
        )
