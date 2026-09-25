import hashlib
import os
import shutil
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import click

from zep_dev.k8s import KUBECONF_PATH
from zep_dev.shared import execute

STATE_ROOT = Path("/tmp") / "zep-dev-terraform-state"


def resolve_root(root: Path) -> Path:
    absolute_root = root.resolve()
    if not absolute_root.exists():
        raise FileNotFoundError(f"Terraform root does not exist: {absolute_root}")
    if not absolute_root.is_dir():
        raise NotADirectoryError(
            f"Terraform root is not a directory: {absolute_root}"
        )
    return absolute_root


def terraform_state_path(root: Path, namespace: str) -> Path:
    state_key = hashlib.sha256(f"{root}\0{namespace}".encode()).hexdigest()
    return STATE_ROOT / state_key / "terraform.tfstate"


@contextmanager
def terraform_environment() -> Generator[dict[str, str]]:
    with TemporaryDirectory(prefix="zep-dev-terraform-") as temporary_directory:
        temporary_root = Path(temporary_directory)
        home = temporary_root / "home"
        data = temporary_root / "data"
        cli_config = temporary_root / "terraform.tfrc"

        home.mkdir()
        data.mkdir()
        cli_config.touch()

        yield {
            "PATH": os.environ.get("PATH", os.defpath),
            "KUBECONFIG": str(KUBECONF_PATH),
            "KUBE_CONFIG_PATH": str(KUBECONF_PATH),
            "HOME": str(home),
            "TF_DATA_DIR": str(data),
            "TF_CLI_CONFIG_FILE": str(cli_config),
        }


def terraform_init(root: Path, env: Mapping[str, str]) -> None:
    args = [
        "terraform",
        f"-chdir={root}",
        "init",
        "-backend=false",
        "-input=false",
    ]
    if (root / ".terraform.lock.hcl").is_file():
        args.append("-lockfile=readonly")
    execute(*args, env=env)


def apply_terraform(root: Path, namespace: str) -> None:
    absolute_root = resolve_root(root)
    state = terraform_state_path(absolute_root, namespace)

    with terraform_environment() as env:
        STATE_ROOT.mkdir(exist_ok=True, parents=True, mode=0o700)
        STATE_ROOT.chmod(0o700)
        state.parent.mkdir(exist_ok=True, mode=0o700)
        state.parent.chmod(0o700)
        terraform_init(absolute_root, env)
        execute(
            "terraform",
            f"-chdir={absolute_root}",
            "apply",
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={namespace}",
            env=env,
        )


def destroy_terraform(root: Path, namespace: str) -> None:
    absolute_root = resolve_root(root)
    state = terraform_state_path(absolute_root, namespace)
    if not state.is_file():
        raise FileNotFoundError(f"Terraform state does not exist: {state}")

    with terraform_environment() as env:
        terraform_init(absolute_root, env)
        execute(
            "terraform",
            f"-chdir={absolute_root}",
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={namespace}",
            env=env,
        )

    shutil.rmtree(state.parent)


@click.command("apply")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to the Terraform root module",
)
@click.option(
    "--namespace",
    required=True,
    help="Kubernetes namespace targeted by Terraform",
)
def apply(root: Path, namespace: str) -> None:
    """Apply Terraform to the managed Kind cluster."""
    apply_terraform(root, namespace)


@click.command("destroy")
@click.option(
    "--root",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to the Terraform root module",
)
@click.option(
    "--namespace",
    required=True,
    help="Kubernetes namespace targeted by Terraform",
)
def destroy(root: Path, namespace: str) -> None:
    """Destroy Terraform resources in the managed Kind cluster."""
    destroy_terraform(root, namespace)
