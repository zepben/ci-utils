import logging
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

import click

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


def download(url: str, dest: Path, *, label: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as response:
        total = int(response.headers.get("Content-Length", -1))
        length = total if total > 0 else None
        with (
            open(dest, "wb") as out,
            click.progressbar(  # type: ignore[var-annotated]
                length=length,
                label=label or dest.name,
                show_eta=length is not None,
            ) as bar,
        ):
            while chunk := response.read(8192):
                out.write(chunk)
                bar.update(len(chunk))


def install_binary_tool(tool: RequiredTool, tools_dir: Path) -> Path:
    url = tool.url.format(version=tool.version)
    dest = tools_dir / tool.name
    if tool.archive_member is None:
        download(url, dest, label=tool.name)
    else:
        member = tool.archive_member.format(version=tool.version)
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            archive = work / "archive.tar.gz"
            download(url, archive, label=tool.name)
            with tarfile.open(archive, "r:gz") as tar:
                tar.extractall(work)
            shutil.copy2(work / member, dest)

    dest.chmod(0o755)
    LOG.info("Installed %s %s -> %s", tool.name, tool.version, dest)
    return dest


@click.command("install")
def install() -> None:
    bin_dir = get_bin_dir()
    bin_dir.mkdir(parents=True, exist_ok=True)

    hash_dir = get_hash_dir()
    hash_dir.mkdir(parents=True, exist_ok=True)
    LOG.info(f"Installing tools to: {bin_dir}")
    for tool in TOOLS:
        if tool.exists(hash_dir=hash_dir):
            LOG.info(f"Skipping already installed tool: {tool.name}")
        else:
            install_binary_tool(tool, bin_dir)
            tool.write_hash(hash_dir=hash_dir)
    LOG.info(f"Installed {len(TOOLS)} tool(s) to {bin_dir.resolve()}")
    LOG.info(f"export PATH={bin_dir.resolve()}:$PATH")


@click.command("uninstall")
def uninstall() -> None:
    tools_dir = get_tools_dir()
    click.confirm(f"Are you sure you want to nuke: {tools_dir}?", abort=True)
    shutil.rmtree(tools_dir)
