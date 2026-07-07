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


class ClusterComponents(BaseModel):
    model_config = ConfigDict(extra="forbid")
    helm_repos: dict[str, str]
    cluster_components: list[ClusterComponent]

    @classmethod
    def from_text_io(cls, input_data: TextIO) -> Self:
        data: Any = yaml.safe_load(input_data.read())
        return cls.model_validate(data)
