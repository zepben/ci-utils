"""Names that identify local Environments and Kubernetes resources."""

from typing import Annotated

from pydantic import AfterValidator, Field

_DNS_LABEL = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
CLUSTER_PREFIX = "zep-dev-"

type NonEmptyStr = Annotated[str, Field(min_length=1)]


def valid_environment_name(name: str) -> str:
    if len(CLUSTER_PREFIX + name) > 63:
        raise ValueError(
            "metadata.name makes the derived Kind cluster name exceed 63 characters"
        )
    return name


type EnvironmentName = Annotated[
    str,
    Field(min_length=1, max_length=63, pattern=_DNS_LABEL),
    AfterValidator(valid_environment_name),
]

type KubernetesName = Annotated[
    str, Field(min_length=1, max_length=63, pattern=_DNS_LABEL)
]


def valid_helm_release(name: str) -> str:
    if len(name) > 53:
        raise ValueError("Helm release names must be at most 53 characters")
    return name
