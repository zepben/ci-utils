"""Distribution schema, chart selections, and application ordering."""

from collections.abc import Iterator
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    field_validator,
)

from zep_dev.development_environments.names import NonEmptyStr

type ChartName = Literal["ewb", "eas", "hcs", "eas-web-client"]

GHCR_REGISTRY = "ghcr.io"
APP_HELM_TIMEOUT = "10m"

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


class BranchLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    branch: NonEmptyStr


class CommitLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commit: FullCommitSha


class LocalLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    local: Literal[True]

    @field_validator("local", mode="before")
    @classmethod
    def require_true(cls, value: object) -> object:
        if value is not True:
            raise ValueError("local must be true")
        return value


# Each locator has one field.
# YAML such as {version: "1.0.0"} is valid.
# Two keys in one locator are rejected.
# https://docs.pydantic.dev/latest/concepts/unions/
type ChartLocator = (
    VersionLocator | PullRequestLocator | BranchLocator | CommitLocator | LocalLocator
)

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
