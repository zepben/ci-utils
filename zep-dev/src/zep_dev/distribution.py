from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, Literal, Self, TextIO

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
)

type ChartName = Literal["ewb", "eas", "hcs", "eas-web-client"]

CHART_OCI_PREFIX = "oci://ghcr.io/zepben/charts"
GHCR_REGISTRY = "ghcr.io"
APP_HELM_TIMEOUT = "10m"

type NonEmptyStr = Annotated[str, Field(min_length=1)]

type FullCommitSha = Annotated[
    str,
    Field(min_length=40, max_length=40, pattern=r"^[0-9a-f]{40}$"),
]


class VersionLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: NonEmptyStr


class PullRequestLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pullRequest: PositiveInt


class CommitLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit: FullCommitSha


# Each locator has one field.
# YAML such as {version: "1.0.0"} is valid.
# Two keys in one locator are rejected.
# https://docs.pydantic.dev/latest/concepts/unions/
type ChartLocator = VersionLocator | PullRequestLocator | CommitLocator

type Charts = Annotated[dict[ChartName, ChartLocator], Field(min_length=1)]

# Preserve the build and install order independently of YAML mapping order.
CHART_ORDER: tuple[ChartName, ...] = ("ewb", "eas", "hcs", "eas-web-client")


def ordered_charts(
    charts: Charts,
) -> Iterator[tuple[ChartName, ChartLocator]]:
    for name in CHART_ORDER:
        if name in charts:
            yield name, charts[name]


class DistributionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr


class Distribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: DistributionMetadata
    charts: Charts

    @classmethod
    def from_text_io(cls, input_data: TextIO) -> Self:
        data: Any = yaml.safe_load(input_data.read())
        return cls.model_validate(data)

    @classmethod
    def from_path(cls, path: Path) -> Self:
        with path.open(encoding="utf-8") as input_data:
            return cls.from_text_io(input_data)
