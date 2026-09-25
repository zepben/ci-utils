"""Distribution and Profile YAML models and loaders."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated, Any, Literal, Self, TextIO

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PositiveInt,
    PrivateAttr,
    TypeAdapter,
    model_validator,
)

from zep_dev.bindings import Bindings
from zep_dev.cluster import CLUSTER_NAME as RESERVED_CLUSTER_NAME
from zep_dev.models import (
    CiSecret,
    ClusterComponentItem,
    ClusterComponents,
    CnpgComponent,
    ContractId,
    HostMount,
)

ComponentName = Literal["ewb", "eas", "hcs", "eas-web-client"]

CHART_OCI_PREFIX = "oci://ghcr.io/zepben/charts"
GHCR_REGISTRY = "ghcr.io"
APP_HELM_TIMEOUT = "10m"

NonEmptyStr = Annotated[str, Field(min_length=1)]

# Kind uses metadata.name as the cluster name, so it must match Kind's naming rules.
_DNS1123_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"


def _reject_reserved_cluster_name(name: str) -> str:
    if name == RESERVED_CLUSTER_NAME:
        raise ValueError(
            f"metadata.name must not be '{RESERVED_CLUSTER_NAME}' "
            "(reserved for chart-test / cluster create)"
        )
    return name


Dns1123Label = Annotated[
    str,
    Field(min_length=1, max_length=63, pattern=_DNS1123_PATTERN),
    AfterValidator(_reject_reserved_cluster_name),
]

FullCommitSha = Annotated[
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


# Each locator is a one-field model so YAML like `{version: "1.0.0"}` is
# accepted, and giving two keys at once is rejected.
# https://docs.pydantic.dev/latest/concepts/unions/
type ComponentLocator = VersionLocator | PullRequestLocator | CommitLocator

COMPONENT_LOCATOR_ADAPTER: TypeAdapter[ComponentLocator] = TypeAdapter(ComponentLocator)

_COMPONENT_ATTRS: tuple[tuple[str, ComponentName], ...] = (
    ("ewb", "ewb"),
    ("eas", "eas"),
    ("hcs", "hcs"),
    ("eas_web_client", "eas-web-client"),
)


class Components(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    ewb: ComponentLocator | None = None
    eas: ComponentLocator | None = None
    hcs: ComponentLocator | None = None
    eas_web_client: ComponentLocator | None = Field(
        default=None, alias="eas-web-client"
    )

    @model_validator(mode="after")
    def at_least_one_component(self) -> Self:
        if not self.present_keys():
            raise ValueError(
                "components must include at least one of: ewb, eas, hcs, eas-web-client"
            )
        return self

    def present_keys(self) -> set[ComponentName]:
        return {name for name, _ in self.iter_locators()}

    def iter_locators(self) -> Iterator[tuple[ComponentName, ComponentLocator]]:
        for attr, yaml_key in _COMPONENT_ATTRS:
            locator: ComponentLocator | None = getattr(self, attr)
            if locator is not None:
                yield yaml_key, locator


class DistributionMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyStr


class Distribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: DistributionMetadata
    components: Components

    @classmethod
    def from_text_io(cls, input_data: TextIO) -> Self:
        data: Any = yaml.safe_load(input_data.read())
        return cls.model_validate(data)

    @classmethod
    def from_path(cls, path: Path) -> Self:
        with path.open(encoding="utf-8") as input_data:
            return cls.from_text_io(input_data)


class ProfileMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Dns1123Label


class KindHostMount(BaseModel):
    """Portable mount intent: slot name resolved via Bindings at apply time."""

    model_config = ConfigDict(extra="forbid")

    slot: NonEmptyStr
    node_path: NonEmptyStr


class KindConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]
    host_mounts: list[KindHostMount] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_cluster_config(self) -> Self:
        if (
            self.config.get("kind") != "Cluster"
            or self.config.get("apiVersion") != "kind.x-k8s.io/v1alpha4"
        ):
            raise ValueError("kind.config must be an inline Kind Cluster mapping")
        slots = [mount.slot for mount in self.host_mounts]
        if len(slots) != len(set(slots)):
            raise ValueError("kind.host_mounts slot names must be unique")
        return self


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, Any] = Field(default_factory=dict)


class TerraformSettings(BaseModel):
    """Which production runtime-contract modules to apply.

    The deployments checkout path lives in Bindings.deployments_root.
    """

    model_config = ConfigDict(extra="forbid")

    contracts: list[ContractId] = Field(min_length=1)

    @model_validator(mode="after")
    def contracts_unique(self) -> Self:
        if len(self.contracts) != len(set(self.contracts)):
            raise ValueError("terraform.contracts must not contain duplicates")
        return self


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    metadata: ProfileMetadata
    distribution: Distribution
    namespace: NonEmptyStr
    kind: KindConfig
    helm_repos: dict[str, str] = Field(default_factory=dict)
    cluster_components: list[ClusterComponentItem] = Field(default_factory=list)
    apps: dict[ComponentName, AppSettings] = Field(default_factory=dict)
    secrets: list[CiSecret] = Field(default_factory=list)
    terraform: TerraformSettings | None = None
    _source_dir: Path | None = PrivateAttr(default=None)

    @property
    def source_dir(self) -> Path | None:
        return self._source_dir

    @model_validator(mode="after")
    def validate_apps_and_component_names(self) -> Self:
        component_keys = self.distribution.components.present_keys()
        apps_outside = set(self.apps) - component_keys
        if apps_outside:
            raise ValueError(
                f"apps keys must be a subset of distribution components; "
                f"not in distribution: {sorted(apps_outside)}"
            )

        helper_names = [c.name for c in self.cluster_components]
        if len(helper_names) != len(set(helper_names)):
            raise ValueError("duplicate cluster_components name")

        collisions = component_keys & set(helper_names)
        if collisions:
            raise ValueError(
                "app release names must not collide with cluster_components names: "
                f"{sorted(collisions)}"
            )
        for component in self.cluster_components:
            if (
                isinstance(component, CnpgComponent)
                and component.namespace != self.namespace
            ):
                raise ValueError(f"CNPG {component.name} must use profile.namespace")
        return self

    @classmethod
    def from_path(cls, path: Path) -> Self:
        with path.open(encoding="utf-8") as input_data:
            raw: Any = yaml.safe_load(input_data.read())
        if not isinstance(raw, dict):
            raise ValueError("Profile YAML must be a mapping")

        distribution_ref = raw.get("distribution")
        if not isinstance(distribution_ref, str) or not distribution_ref:
            raise ValueError("distribution must be a non-empty path string")

        distribution_path = (path.parent / distribution_ref).resolve()
        distribution = Distribution.from_path(distribution_path)

        profile = cls.model_validate({**raw, "distribution": distribution})
        profile._source_dir = path.parent.resolve()
        return profile

    def to_cluster_components(self) -> ClusterComponents:
        """Helpers install view used by platform apply (same schema as cluster create)."""
        components = ClusterComponents(
            helm_repos=self.helm_repos,
            cluster_components=list(self.cluster_components),
        )
        components._source_dir = self.source_dir
        return components

    def resolved_host_mounts(self, bindings: Bindings) -> list[HostMount]:
        """Resolve Profile mount slots through Bindings to Kind HostMounts."""
        mounts: list[HostMount] = []
        for entry in self.kind.host_mounts:
            host_path = bindings.require_mount(entry.slot).resolve()
            if not host_path.is_dir():
                raise ValueError(
                    f"bindings.mounts.{entry.slot} is not a directory: {host_path}"
                )
            mounts.append(
                HostMount(
                    host_path=host_path,
                    node_path=entry.node_path,
                    read_only=False,
                )
            )
        return mounts

    def requires_bindings(self) -> bool:
        """True when Apply must load Bindings (mounts and/or terraform)."""
        return bool(self.kind.host_mounts) or self.terraform is not None


def load_profile_metadata(path: Path) -> ProfileMetadata:
    """Read only metadata.name from a Profile file.

    Used by platform destroy so we can tear down a cluster even when the
    Distribution path is missing or the rest of the Profile is invalid.
    """
    with path.open(encoding="utf-8") as input_data:
        raw: Any = yaml.safe_load(input_data.read())
    if not isinstance(raw, dict):
        raise ValueError("Profile YAML must be a mapping")
    if "metadata" not in raw:
        raise ValueError("Profile YAML missing metadata")
    return ProfileMetadata.model_validate(raw["metadata"])
