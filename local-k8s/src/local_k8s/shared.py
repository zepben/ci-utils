import logging
import os
import subprocess
import sys
from pathlib import Path

from local_k8s.models import RequiredTool

LOG = logging.getLogger(__name__)

TOOLS: list[RequiredTool] = [
    RequiredTool(
        name="helm",
        version="v4.2.2",
        url="https://get.helm.sh/helm-{version}-linux-amd64.tar.gz",
        archive_member="linux-amd64/helm",
    ),
    RequiredTool(
        name="ct",
        version="3.14.0",
        url=(
            "https://github.com/helm/chart-testing/releases/download/"
            "v{version}/chart-testing_{version}_linux_amd64.tar.gz"
        ),
        archive_member="ct",
    ),
    RequiredTool(
        name="kubeconform",
        version="v0.8.0",
        url=(
            "https://github.com/yannh/kubeconform/releases/download/"
            "{version}/kubeconform-linux-amd64.tar.gz"
        ),
        archive_member="kubeconform",
    ),
    RequiredTool(
        name="kind",
        version="v0.32.0",
        url="https://kind.sigs.k8s.io/dl/{version}/kind-linux-amd64",
    ),
    RequiredTool(
        name="kubectl",
        version="v1.36.2",
        url="https://dl.k8s.io/release/{version}/bin/linux/amd64/kubectl",
    ),
    RequiredTool(
        name="shellcheck",
        version="v0.11.0",
        url=(
            "https://github.com/koalaman/shellcheck/releases/download/"
            "{version}/shellcheck-{version}.linux.x86_64.tar.gz"
        ),
        archive_member="shellcheck-{version}/shellcheck",
    ),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}


def get_repo_name() -> str:
    if sys.prefix == sys.base_prefix:
        raise Exception("local-k8s must be run from an application virtualenv")
    return Path(sys.prefix).resolve().parent.name


def get_tools_dir() -> Path:
    repo_name = get_repo_name()
    return Path.home() / ".local" / "share" / repo_name


def get_bin_dir() -> Path:
    return get_tools_dir() / "bin"


def get_hash_dir() -> Path:
    return get_tools_dir() / "hash"


def resolve(name: str) -> str:
    tool = TOOLS_BY_NAME.get(name)
    if tool is None:
        raise Exception(f"Failed to locate tool: {name}")
    path = get_bin_dir() / tool.name
    if not path.is_file() or not os.access(path, os.X_OK):
        raise Exception(f"{name} not installed at {path}; run: local-k8s tools install")
    return str(path)


def execute(*args: str) -> str:
    arg_list = list(args)
    arg_list[0] = resolve(args[0])
    LOG.debug("Executing: %s", arg_list)
    return subprocess.check_output(arg_list, text=True)
