from contextlib import suppress
from pathlib import Path
from typing import Any, Self, TextIO

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
