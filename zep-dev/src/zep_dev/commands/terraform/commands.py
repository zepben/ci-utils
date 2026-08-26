import hashlib
import os
import shutil
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import click

from zep_dev.k8s import kube_guard
from zep_dev.shared import execute

STATE_ROOT = Path("/tmp") / "zep-dev-terraform-state"


def resolve_root(root: Path) -> Path:
    absolute_root = root.resolve()
    if not absolute_root.exists():
        raise click.ClickException(f"Terraform root does not exist: {absolute_root}")
    if not absolute_root.is_dir():
        raise click.ClickException(
            f"Terraform root is not a directory: {absolute_root}"
        )
    return absolute_root


def terraform_state_path(root: Path, namespace: str) -> Path:
    state_key = hashlib.sha256(f"{root}\0{namespace}".encode()).hexdigest()
    return STATE_ROOT / state_key / "terraform.tfstate"


@contextmanager
def disposable_workdir() -> Generator[None]:
    with TemporaryDirectory(prefix="zep-dev-terraform-data-") as temporary_directory:
        os.environ["TF_DATA_DIR"] = str(Path(temporary_directory) / "data")
        with kube_guard():
            yield


def terraform_init(root: Path) -> None:
    execute(
        "terraform",
        f"-chdir={root}",
        "init",
        "-backend=false",
        "-input=false",
        "-lockfile=readonly",
    )


def apply_terraform(root: Path, namespace: str) -> None:
    absolute_root = resolve_root(root)
    state = terraform_state_path(absolute_root, namespace)

    with disposable_workdir():
        STATE_ROOT.mkdir(exist_ok=True, parents=True)
        terraform_init(absolute_root)
        execute(
            "terraform",
            f"-chdir={absolute_root}",
            "apply",
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={namespace}",
        )


def destroy_terraform(root: Path, namespace: str) -> None:
    absolute_root = resolve_root(root)
    state = terraform_state_path(absolute_root, namespace)
    if not state.is_file():
        raise click.ClickException(f"Terraform state does not exist: {state}")

    with disposable_workdir():
        terraform_init(absolute_root)
        execute(
            "terraform",
            f"-chdir={absolute_root}",
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={namespace}",
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
