"""Environment Template schema and cross-reference validation."""

from pathlib import PurePosixPath
from typing import Literal, Self, assert_never

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zep_dev.development_environments.distributions import (
    ChartName,
    Distribution,
)
from zep_dev.development_environments.names import (
    EnvironmentName,
    KubernetesName,
    NonEmptyStr,
    valid_helm_release,
)
from zep_dev.development_environments.services import (
    CnpgService,
    DatabaseService,
    HelmService,
    RawService,
    SupportingService,
)


class TemplateMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: EnvironmentName


class MountSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: NonEmptyStr
    node_path: NonEmptyStr

    @model_validator(mode="after")
    def absolute_node_path(self) -> Self:
        if not PurePosixPath(self.node_path).is_absolute():
            raise ValueError("node_path must be absolute")
        return self


class KindMount(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    hostPath: str
    containerPath: str
    readOnly: bool = False


class KindNode(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    role: Literal["control-plane", "worker"]
    extraMounts: list[KindMount] = Field(default_factory=list)


class KindConfig(BaseModel):
    # Kind options outside the fields consumed here remain available to Kind.
    model_config = ConfigDict(extra="allow", strict=True)

    kind: Literal["Cluster"]
    apiVersion: Literal["kind.x-k8s.io/v1alpha4"]
    nodes: list[KindNode] = Field(default_factory=list)


class ClusterConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: KindConfig
    mounts: list[MountSlot] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_cluster(self) -> Self:
        slots = [mount.slot for mount in self.mounts]
        node_paths = [mount.node_path for mount in self.mounts]
        if len(node_paths) != len(set(node_paths)):
            raise ValueError("cluster.mounts node paths must be unique")
        if len(slots) != len(set(slots)):
            raise ValueError("cluster.mounts slot names must be unique")
        if self.mounts and not any(node.role == "worker" for node in self.kind.nodes):
            raise ValueError("cluster.mounts requires a Kind worker node")
        return self


class DatabaseReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: KubernetesName
    database: NonEmptyStr


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    values: dict[str, object] = Field(default_factory=dict)
    databases: dict[NonEmptyStr, DatabaseReference] = Field(default_factory=dict)
    manifests: list[NonEmptyStr] = Field(default_factory=list)


class SecretInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: KubernetesName


class TemplateInputs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mounts: list[NonEmptyStr] = Field(default_factory=list)
    repositories: list[NonEmptyStr] = Field(default_factory=list)
    secrets: dict[NonEmptyStr, SecretInput] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_inputs(self) -> Self:
        for field, values in (
            ("mounts", self.mounts),
            ("repositories", self.repositories),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"inputs.{field} contains duplicates")
        names = [secret.name for secret in self.secrets.values()]
        if len(names) != len(set(names)):
            raise ValueError(
                "inputs.secrets contains duplicate Kubernetes Secret names"
            )
        return self


class EnvironmentTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metadata: TemplateMetadata
    distribution: NonEmptyStr | None = None
    cluster: ClusterConfig
    services: dict[KubernetesName, SupportingService] = Field(default_factory=dict)
    applications: dict[ChartName, ApplicationConfig] = Field(default_factory=dict)
    inputs: TemplateInputs = Field(default_factory=TemplateInputs)

    @model_validator(mode="after")
    def valid_references(self) -> Self:
        if self.distribution is None and self.applications:
            raise ValueError("applications requires a Distribution")
        self.validate_mount_references()
        self.validate_service_references()
        self.validate_database_references()
        return self

    def validate_mount_references(self) -> None:
        mounted = set(self.inputs.mounts)
        for mount in self.cluster.mounts:
            if mount.slot not in mounted:
                raise ValueError(
                    f"cluster.mounts.{mount.slot} is not declared in inputs.mounts"
                )
        used_mounts = {mount.slot for mount in self.cluster.mounts}
        if mounted - used_mounts:
            raise ValueError(
                f"inputs.mounts has no consumer: {sorted(mounted - used_mounts)}"
            )

    def validate_service_references(self) -> None:
        for name, service in self.services.items():
            if not isinstance(service, HelmService):
                continue
            valid_helm_release(name)
            if service.integration is None:
                continue
            unknown = set(service.integration.repositories) - set(
                self.inputs.repositories
            )
            if unknown:
                raise ValueError(
                    f"services.{name}.integration.repositories undeclared: {sorted(unknown)}"
                )

    def validate_database_references(self) -> None:
        for app, config in self.applications.items():
            for name, reference in config.databases.items():
                path = f"applications.{app}.databases.{name}"
                service = self.database_service(reference.service)
                if service is None:
                    raise ValueError(
                        f"{path}.service must name a database service: {reference.service}"
                    )
                if (
                    reference.database != service.database
                    and reference.database not in service.databases
                ):
                    raise ValueError(
                        f"{path}.database is not declared by service {reference.service}: {reference.database}"
                    )

    def database_service(self, name: str) -> DatabaseService | None:
        service = self.services.get(name)
        match service:
            case HelmService() | RawService() | None:
                return None
            case CnpgService():
                return service
            case _:
                assert_never(service)


def validate_distribution(
    template: EnvironmentTemplate, distribution: Distribution | None
) -> None:
    if (template.distribution is None) != (distribution is None):
        raise ValueError(
            "Template Distribution reference and loaded Distribution disagree"
        )
    if distribution is None:
        return
    unknown = set(template.applications) - set(distribution.charts)
    if unknown:
        raise ValueError(
            f"applications not selected by Distribution: {sorted(unknown)}"
        )
    collisions = set(template.services) & set(distribution.charts)
    if collisions:
        raise ValueError(
            f"service names collide with application releases: {sorted(collisions)}"
        )
