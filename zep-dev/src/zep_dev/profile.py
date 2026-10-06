"""How a Distribution runs as a Kind Deployment.

Layer details: docs/distribution-profile-bindings.md.
"""

from pathlib import Path
from typing import Annotated, Any, Self

import yaml
from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    PrivateAttr,
    model_validator,
)

from zep_dev.bindings import Bindings
from zep_dev.cluster import CLUSTER_NAME as RESERVED_CLUSTER_NAME
from zep_dev.distribution import ChartName, Distribution, NonEmptyStr
from zep_dev.models import (
    CiSecret,
    ClusterComponentItem,
    CnpgComponent,
    DatabaseApp,
    HostMount,
)

_DNS1123_PATTERN = r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"


def reject_reserved_cluster_name(name: str) -> str:
    if name == RESERVED_CLUSTER_NAME:
        raise ValueError(
            f"metadata.name must not be '{RESERVED_CLUSTER_NAME}' "
            "(reserved for chart-test / cluster create)"
        )
    return name


type Dns1123Label = Annotated[
    str,
    Field(min_length=1, max_length=63, pattern=_DNS1123_PATTERN),
    AfterValidator(reject_reserved_cluster_name),
]


class ProfileMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Dns1123Label


class MountSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: NonEmptyStr
    node_path: NonEmptyStr


class KindCluster(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]

    @model_validator(mode="after")
    def valid_cluster_config(self) -> Self:
        if (
            self.config.get("kind") != "Cluster"
            or self.config.get("apiVersion") != "kind.x-k8s.io/v1alpha4"
        ):
            raise ValueError("k8s.kind.config must be an inline Kind Cluster mapping")
        return self


class K8sConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: KindCluster
    mounts: list[MountSlot] = Field(default_factory=list)
    helm_repos: dict[str, str] = Field(default_factory=dict)
    components: list[ClusterComponentItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_mount_slots(self) -> Self:
        slots = [mount.slot for mount in self.mounts]
        if len(slots) != len(set(slots)):
            raise ValueError("k8s.mounts slot names must be unique")
        return self


class RuntimeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    namespace: NonEmptyStr
    files: list[NonEmptyStr] = Field(min_length=1)


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    databases: dict[DatabaseApp, NonEmptyStr] = Field(default_factory=dict)
    manifests: list[RuntimeManifest] = Field(default_factory=list)


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    metadata: ProfileMetadata
    distribution: Distribution
    namespace: NonEmptyStr
    k8s: K8sConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    apps: dict[ChartName, dict[str, Any]] = Field(default_factory=dict)
    secrets: list[CiSecret] = Field(default_factory=list)
    _source_dir: Path | None = PrivateAttr(default=None)

    @property
    def source_dir(self) -> Path | None:
        return self._source_dir

    @model_validator(mode="after")
    def validate_layers(self) -> Self:
        chart_keys = self.distribution.charts.keys()
        apps_outside = set(self.apps) - chart_keys
        if apps_outside:
            raise ValueError(
                f"apps keys must be a subset of distribution charts; "
                f"not in distribution: {sorted(apps_outside)}"
            )

        helper_names = [c.name for c in self.k8s.components]
        if len(helper_names) != len(set(helper_names)):
            raise ValueError("duplicate k8s.components name")

        collisions = chart_keys & set(helper_names)
        if collisions:
            raise ValueError(
                "app release names must not collide with k8s.components names: "
                f"{sorted(collisions)}"
            )

        cnpg_names = {
            c.name for c in self.k8s.components if isinstance(c, CnpgComponent)
        }
        for app, binding in self.runtime.databases.items():
            if binding not in cnpg_names:
                raise ValueError(
                    f"runtime.databases.{app}={binding!r} "
                    f"must name a k8s CNPG component; "
                    f"known: {sorted(cnpg_names) or '(none)'}"
                )

        for component in self.k8s.components:
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

    def resolved_host_mounts(self, bindings: Bindings) -> list[HostMount]:
        mounts: list[HostMount] = []
        for entry in self.k8s.mounts:
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
        return bool(self.k8s.mounts) or bool(self.runtime.databases)

    def cnpg(self, name: str) -> CnpgComponent:
        for component in self.k8s.components:
            if isinstance(component, CnpgComponent) and component.name == name:
                return component
        raise KeyError(f"no k8s CNPG component named {name!r}")


def load_profile_metadata(path: Path) -> ProfileMetadata:
    """Read metadata.name only.

    Destroy does not need a valid Distribution.
    """
    with path.open(encoding="utf-8") as input_data:
        raw: Any = yaml.safe_load(input_data.read())
    if not isinstance(raw, dict):
        raise ValueError("Profile YAML must be a mapping")
    if "metadata" not in raw:
        raise ValueError("Profile YAML missing metadata")
    return ProfileMetadata.model_validate(raw["metadata"])
