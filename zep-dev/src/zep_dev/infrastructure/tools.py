"""Managed-tool definitions, installation identity, paths and executable resolution."""

import os
import sys
from contextlib import suppress
from enum import StrEnum
from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from zep_dev.errors import ZepDevError


class ArchiveFormat(StrEnum):
    NONE = "none"
    TAR_GZ = "tar.gz"
    ZIP = "zip"


class RequiredTool(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    version: str
    url: str
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    archive_member: str | None = None
    archive_format: ArchiveFormat = ArchiveFormat.NONE

    @model_validator(mode="after")
    def validate_archive_configuration(self) -> Self:
        has_archive = self.archive_format is not ArchiveFormat.NONE
        if has_archive != (self.archive_member is not None):
            raise ValueError("archive_member and archive_format must be set together")
        return self

    def to_hash(self) -> str:
        return f"{self.name}-{self.version}-{self.url}-{self.sha256}"

    def exists(self, hash_dir: Path) -> bool:
        with suppress(OSError):
            return (hash_dir / self.name).read_text() == self.to_hash()
        return False

    def write_hash(self, hash_dir: Path) -> None:
        (hash_dir / self.name).write_text(self.to_hash())


TOOLS: list[RequiredTool] = [
    RequiredTool(
        name="helm",
        version="v4.2.2",
        url="https://get.helm.sh/helm-{version}-linux-amd64.tar.gz",
        sha256="9adafecab4d406853bba163a70e9f104f47dbbf65ce24b7653bae7e36150bcb6",
        archive_member="linux-amd64/helm",
        archive_format=ArchiveFormat.TAR_GZ,
    ),
    RequiredTool(
        name="ct",
        version="3.14.0",
        url=(
            "https://github.com/helm/chart-testing/releases/download/"
            "v{version}/chart-testing_{version}_linux_amd64.tar.gz"
        ),
        sha256="d16f0583616885423826241164ce1f6589c6fe5332fa74f374ebd2bd3cb3fe1f",
        archive_member="ct",
        archive_format=ArchiveFormat.TAR_GZ,
    ),
    RequiredTool(
        name="kubeconform",
        version="v0.8.0",
        url=(
            "https://github.com/yannh/kubeconform/releases/download/"
            "{version}/kubeconform-linux-amd64.tar.gz"
        ),
        sha256="9bc2bffbf71f261128533edaf912153948b7ff238f9a531ae6d34466ec287883",
        archive_member="kubeconform",
        archive_format=ArchiveFormat.TAR_GZ,
    ),
    RequiredTool(
        name="kind",
        version="v0.32.0",
        url="https://kind.sigs.k8s.io/dl/{version}/kind-linux-amd64",
        sha256="50030de23cf40a18505f20426f6a8506bedf13c6e509244bd1fa9463721b0f54",
    ),
    RequiredTool(
        name="kubectl",
        version="v1.36.2",
        url="https://dl.k8s.io/release/{version}/bin/linux/amd64/kubectl",
        sha256="1e9045ec32bea85da43de85f0065358529ea7c7a152eca78154fba5b58c27d82",
    ),
    RequiredTool(
        name="shellcheck",
        version="v0.11.0",
        url=(
            "https://github.com/koalaman/shellcheck/releases/download/"
            "{version}/shellcheck-{version}.linux.x86_64.tar.gz"
        ),
        sha256="b7af85e41cc99489dcc21d66c6d5f3685138f06d34651e6d34b42ec6d54fe6f6",
        archive_member="shellcheck-{version}/shellcheck",
        archive_format=ArchiveFormat.TAR_GZ,
    ),
    RequiredTool(
        name="chainsaw",
        version="0.2.15",
        url=(
            "https://github.com/kyverno/chainsaw/releases/download/"
            "v{version}/chainsaw_linux_amd64.tar.gz"
        ),
        sha256="295d226c89f126c0a97775d364be149f47a810c8a3f9829ee410583d0c1abe3c",
        archive_member="chainsaw",
        archive_format=ArchiveFormat.TAR_GZ,
    ),
    RequiredTool(
        name="argocd",
        version="v3.3.6",
        url=(
            "https://github.com/argoproj/argo-cd/releases/download/"
            "{version}/argocd-linux-amd64"
        ),
        sha256="36c243afeb46bbaedec3c9b6823c043a741a36b1b8215147676bb8f18f21ef73",
    ),
    RequiredTool(
        name="terraform",
        version="1.15.9",
        url=(
            "https://releases.hashicorp.com/terraform/{version}/"
            "terraform_{version}_linux_amd64.zip"
        ),
        sha256="76edd0b22d2f27d3d2e097cd793209646f719cf60f02ff3af626b07361137da1",
        archive_member="terraform",
        archive_format=ArchiveFormat.ZIP,
    ),
]
TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def get_repo_name() -> str:
    if sys.prefix == sys.base_prefix:
        raise ZepDevError("zep-dev must be run from an application virtualenv")
    return Path(sys.prefix).resolve().parent.name


def get_tools_dir() -> Path:
    repo_name = get_repo_name()
    return Path.home() / ".local" / "share" / repo_name


def get_bin_dir() -> Path:
    return get_tools_dir() / "bin"


def get_hash_dir() -> Path:
    return get_tools_dir() / "hash"


def resolve(name: str) -> None:
    """
    Ensure we have our required tools present.
    We inject the bin dir in PATH earlier in execution, but
    this acts as a runtime safeguard and prevents accidentally
    adding another tool that is not covered.
    """
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise Exception(f"Failed to locate tool: {name}")
    path = get_bin_dir() / tool.name
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ZepDevError(f"{name} not installed at {path}; run: zep-dev tools install")
