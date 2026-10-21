"""Supporting-service schemas supplied by a Template."""

from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from zep_dev.development_environments.names import KubernetesName, NonEmptyStr


class OciRepository(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: KubernetesName
    registry: NonEmptyStr
    repository: NonEmptyStr


class ArgoIntegration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["argo-cd"]
    repositories: list[NonEmptyStr] = Field(default_factory=list)
    oci_repositories: list[OciRepository] = Field(default_factory=list)


class ConfigMapFromFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: KubernetesName
    from_file: dict[NonEmptyStr, NonEmptyStr] = Field(min_length=1)


class WaitFor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource: NonEmptyStr
    for_: NonEmptyStr = Field(alias="for")
    timeout: NonEmptyStr
    namespace: KubernetesName | None = None


class LoadDbCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_secret: KubernetesName
    database: NonEmptyStr


class HelmService(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["helm"]
    chart: NonEmptyStr
    repository: NonEmptyStr | None = None
    version: NonEmptyStr
    namespace: KubernetesName | None = None
    values: dict[str, object] = Field(default_factory=dict)
    integration: ArgoIntegration | None = None
    config_maps_from_file: list[ConfigMapFromFile] = Field(default_factory=list)
    wait_for: list[WaitFor] = Field(default_factory=list)
    load_db_credentials: LoadDbCredentials | None = None

    @model_validator(mode="after")
    def valid_chart_source(self) -> Self:
        if self.chart.startswith("oci://"):
            parsed = urlsplit(self.chart)
            if not parsed.netloc or not parsed.path.strip("/") or self.repository:
                raise ValueError("OCI chart requires a chart path and no repository")
        else:
            parsed = urlsplit(self.chart)
            repo = urlsplit(self.repository or "")
            if (
                parsed.scheme
                or "/" in self.chart
                or self.chart in {".", ".."}
                or repo.scheme not in {"http", "https"}
                or not repo.netloc
            ):
                raise ValueError(
                    "Helm chart requires a chart name and HTTP(S) repository URL"
                )
        return self

    @field_validator("config_maps_from_file")
    @classmethod
    def unique_config_maps(
        cls, configs: list[ConfigMapFromFile]
    ) -> list[ConfigMapFromFile]:
        names = [config.name for config in configs]
        if len(names) != len(set(names)):
            raise ValueError("duplicate config_maps_from_file name")
        return configs


class CnpgImageCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    major: int = Field(ge=10)
    image: NonEmptyStr


class CnpgDatabase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extensions: list[str] = Field(default_factory=list)


class CnpgService(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["cnpg"]
    namespace: KubernetesName | None = None
    database: NonEmptyStr
    owner: NonEmptyStr
    password: NonEmptyStr
    databases: dict[NonEmptyStr, CnpgDatabase] = Field(default_factory=dict)
    image_catalog: CnpgImageCatalog | None = None
    spec: dict[str, object]

    @model_validator(mode="after")
    def valid_spec(self) -> Self:
        if "bootstrap" in self.spec:
            raise ValueError("spec.bootstrap is generated from database and owner")
        if self.database in self.databases:
            raise ValueError("primary database must not appear in databases")
        if self.image_catalog and (
            "imageName" in self.spec or "imageCatalogRef" in self.spec
        ):
            raise ValueError(
                "image_catalog cannot be combined with spec image selection"
            )
        return self


class RawService(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["raw"]
    manifests: list[NonEmptyStr] = Field(min_length=1)
    wait_timeout: NonEmptyStr = "60s"

    @field_validator("manifests")
    @classmethod
    def https_manifests(cls, manifests: list[str]) -> list[str]:
        for manifest in manifests:
            parsed = urlsplit(manifest)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("raw manifests must contain only HTTPS URLs")
        return manifests


type SupportingService = Annotated[
    HelmService | CnpgService | RawService, Field(discriminator="type")
]
