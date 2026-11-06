"""Callable contracts for fixtures that return helpers."""

from pathlib import Path
from typing import NotRequired, Protocol, TypedDict, Unpack

from tests.support.execution import FakeExecute


class PrepareKind(Protocol):
    def __call__(
        self, *, present: bool = False, name: str = "integration"
    ) -> FakeExecute: ...


class BindingsPayload(TypedDict):
    mounts: NotRequired[dict[str, object]]
    repositories: NotRequired[dict[str, object]]
    secrets: NotRequired[dict[str, object]]


class WriteBindings(Protocol):
    def __call__(self, **groups: Unpack[BindingsPayload]) -> Path: ...


DistributionPayload = TypedDict(
    "DistributionPayload",
    {
        "ewb": dict[str, object],
        "eas": dict[str, object],
        "hcs": dict[str, object],
        "eas-web-client": dict[str, object],
    },
    total=False,
)


class WriteDistribution(Protocol):
    # These helpers accept raw locators, including malformed test inputs.
    def __call__(
        self, filename: str = "dist.yaml", **charts: Unpack[DistributionPayload]
    ) -> Path: ...
