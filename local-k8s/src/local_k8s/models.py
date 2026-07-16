import os
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, Self, TextIO

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ClusterComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    chart: str
    version: str
    namespace: str
    set: dict[str, str] = Field(default_factory=dict)


class RequiredTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    url: str
    archive_member: str | None = None

    def to_hash(self) -> str:
        return f"{self.name}-{self.version}-{self.url}"

    def exists(self, hash_dir: Path) -> bool:
        with suppress(OSError):
            return (hash_dir / self.name).read_text() == self.to_hash()
        return False

    def write_hash(self, hash_dir: Path) -> None:
        (hash_dir / self.name).write_text(self.to_hash())


class ClusterComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    helm_repos: dict[str, str]
    cluster_components: list[ClusterComponent]

    @classmethod
    def from_text_io(cls, input_data: TextIO) -> Self:
        data: Any = yaml.safe_load(input_data.read())
        return cls.model_validate(data)


class CiSecret(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["env-file"]
    env_var: str

    def resolve_path(self) -> Path:
        value = os.environ.get(self.env_var)
        if value is None:
            raise ValueError(f"{self.env_var} is not set. This is required ")
        return Path(value).expanduser()


class CiSecrets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secrets: list[CiSecret]


class ChartMetadata(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    type: str = "application"
    appVersion: str | None = None

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        chart_yaml = chart_dir / "Chart.yaml"
        if not chart_yaml.is_file():
            raise ValueError(f"Chart.yaml not found at {chart_yaml}")
        return cls.model_validate(yaml.safe_load(chart_yaml.read_text()))
