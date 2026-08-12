import os
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Self, TextIO

import yaml
from pydantic import BaseModel, ConfigDict, Field

# Path inside kind workers. Argo file:// URLs and repo-server hostPath both assume it.
LOCAL_REPO_MOUNT_ROOT = "/mnt/local-repos"


@dataclass(frozen=True)
class LocalRepo:
    path: Path

    @property
    def basename(self) -> str:
        return self.path.name

    @property
    def container_path(self) -> str:
        return f"{LOCAL_REPO_MOUNT_ROOT}/{self.basename}"


class OciRepository(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    registry: str = Field(min_length=1)
    repository: str = Field(min_length=1)

    @property
    def url(self) -> str:
        return f"{self.registry}/{self.repository}"


class LocalRepoIntegration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["argo-cd"]
    oci_repositories: list[OciRepository] = Field(default_factory=list)


class ClusterComponent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    chart: str
    version: str
    namespace: str
    local_repo_integration: LocalRepoIntegration | None = None
    values: dict[str, Any] = Field(default_factory=dict)


class RequiredTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    url: str
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    archive_member: str | None = None

    def to_hash(self) -> str:
        return f"{self.name}-{self.version}-{self.url}-{self.sha256}"

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


class ChartTestingConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    remote: str
    target_branch: str = Field(alias="target-branch")
    chart_dirs: list[Path] = Field(alias="chart-dirs")
    chart_repos: list[str] = Field(default_factory=list, alias="chart-repos")
    validate_maintainers: bool = Field(alias="validate-maintainers")
    check_version_increment: bool = Field(alias="check-version-increment")
    namespace: str
    release_label: str = Field(alias="release-label")
    additional_commands: list[str] = Field(
        default_factory=list, alias="additional-commands"
    )

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        chart_yaml = chart_dir / "ct.yaml"
        if not chart_yaml.is_file():
            raise ValueError(f"ct.yaml not found at {chart_yaml}")
        return cls.model_validate(yaml.safe_load(chart_yaml.read_text()))


class CiSecret(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    kind: Literal["env-file"]
    env_var: str

    def resolve_path(self) -> Path:
        value = os.environ.get(self.env_var)
        if value is None:
            raise ValueError(f"{self.env_var} is not set. This is required ")
        return Path(value).expanduser()


class CiSecrets(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secrets: list[CiSecret]


class ChartDependency(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    repository: str = Field(min_length=1)


class ChartMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    type: str = "application"
    appVersion: str | None = None
    annotations: dict[str, str] = Field(default_factory=dict)
    dependencies: list[ChartDependency] = Field(default_factory=list)

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        chart_yaml = chart_dir / "Chart.yaml"
        if not chart_yaml.is_file():
            raise ValueError(f"Chart.yaml not found at {chart_yaml}")
        return cls.model_validate(yaml.safe_load(chart_yaml.read_text()))

    def write(self, chart_dir: Path) -> None:
        (chart_dir / "Chart.yaml").write_text(
            yaml.safe_dump(
                self.model_dump(mode="json", exclude_unset=True),
                sort_keys=False,
            )
        )


class ChartImageValues(BaseModel):
    model_config = ConfigDict(extra="allow")

    tag: str | None = None


class ChartValues(BaseModel):
    model_config = ConfigDict(extra="allow")

    image: ChartImageValues = Field(default_factory=ChartImageValues)

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        values_yaml = chart_dir / "values.yaml"
        if not values_yaml.is_file():
            return cls()
        return cls.model_validate(yaml.safe_load(values_yaml.read_text()))

    def write(self, chart_dir: Path) -> None:
        (chart_dir / "values.yaml").write_text(
            yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)
        )
