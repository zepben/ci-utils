import logging
import platform
import shutil
import subprocess
import sys
import tarfile
from contextlib import suppress
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory

import click
import requests
from requests.exceptions import (
    RequestException,
)
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from local_k8s.models import RequiredTool
from local_k8s.shared import execute, get_bin_dir, get_hash_dir, get_tools_dir
from local_k8s.static import TOOLS

LOG = logging.getLogger(__name__)

DOWNLOAD_TIMEOUT_SECONDS = 60
DOWNLOAD_ATTEMPTS = 5


def download_url(url: str, dest: Path, *, label: str | None = None) -> None:
    with requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response:
        response.raise_for_status()
        length = int(response.headers.get("Content-Length", 0)) or None
        with (
            open(dest, "wb") as out,
            click.progressbar(  # type: ignore[var-annotated]
                length=length,
                label=label or dest.name,
                show_eta=length is not None,
            ) as bar,
        ):
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                out.write(chunk)
                bar.update(len(chunk))


def download(url: str, dest: Path, *, label: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    for attempt in Retrying(
        stop=stop_after_attempt(DOWNLOAD_ATTEMPTS),
        wait=wait_exponential_jitter(initial=1, max=30),
        retry=retry_if_exception_type(RequestException),
        before_sleep=before_sleep_log(LOG, logging.WARNING),
        reraise=True,
    ):
        with attempt:
            try:
                download_url(url, dest, label=label)
            except Exception:
                dest.unlink(missing_ok=True)
                raise


def extract_archive_member(archive: Path, member: str, dest_dir: Path) -> None:
    with tarfile.open(archive, "r:gz") as tar:
        try:
            info = tar.getmember(member)
        except KeyError as exc:
            raise Exception(f"Archive member not found: {member}") from exc
        tar.extract(info, dest_dir, filter="data")


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
            extract_archive_member(archive, member, work)
            shutil.copy2(work / member, dest)

    dest.chmod(0o755)
    LOG.info("Installed %s %s -> %s", tool.name, tool.version, dest)
    return dest


def install_helm_unit_tests() -> None:
    plugins = execute("helm", "plugin", "list", capture_stdout=True)
    LOG.info("Installing helm unit test")
    for line in plugins.stdout.splitlines():
        if line.startswith("unittest"):
            LOG.info("helm unittest already installed, skipping ")
            return
    execute(
        "helm",
        "plugin",
        "install",
        "https://github.com/helm-unittest/helm-unittest",
        "--verify=false",
    )


def install_python_requirements() -> None:
    LOG.info("Installing python requirements")
    resource = files("local_k8s.resources").joinpath("python-requirements.txt")
    with as_file(resource) as requirements:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements), "-qq"],
        )


def install_binary_tools() -> None:
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


@click.command("path")
def path() -> None:
    click.echo(str(get_bin_dir().resolve()))


@click.command("install")
def install() -> None:
    system = platform.system()
    if system != "Linux":
        raise click.ClickException(
            f"{system} is not a supported OS. Please contact #techops for assistance"
        )

    install_binary_tools()
    install_helm_unit_tests()
    install_python_requirements()


@click.command("uninstall")
@click.option("--no-prompt", is_flag=True, help="Do the thing without asking")
def uninstall(no_prompt: bool) -> None:
    tools_dir = get_tools_dir()
    if no_prompt or click.confirm(
        f"Are you sure you want to nuke: {tools_dir}?", abort=True
    ):
        with suppress(FileNotFoundError):
            shutil.rmtree(tools_dir)
            LOG.info(f"Removed {tools_dir}")
