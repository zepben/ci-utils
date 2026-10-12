"""Command-line entry points for development Environments."""

from pathlib import Path

import click

from zep_dev.charts.images import pack_images
from zep_dev.development_environments import images, secrets, terraform
from zep_dev.development_environments.chart_sources import (
    ChartResolver,
    build_distribution,
)
from zep_dev.development_environments.documents import load_distribution
from zep_dev.development_environments.lifecycle import (
    create_environment,
    destroy_environment,
    environment_kubeconfig,
    list_environments,
    require_environment,
)


@click.group(help="Create and manage named development Environments")
def environment() -> None:
    pass


@environment.command("create")
@click.option(
    "--template",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--allow-reuse",
    is_flag=True,
    help="Reuse an existing Environment on a best-effort basis",
)
@click.option("--image-archive", type=click.Path(dir_okay=False, path_type=Path))
def create(template: Path, allow_reuse: bool, image_archive: Path | None) -> None:
    target = create_environment(
        template, allow_reuse=allow_reuse, image_archive=image_archive
    )
    click.echo(f"Environment {target.name} ready", err=True)


@environment.command("list")
def list_environments_command() -> None:
    for name in list_environments():
        click.echo(name)


@environment.command("destroy")
@click.argument("name")
def destroy(name: str) -> None:
    destroy_environment(name)


@environment.command("kubeconfig")
@click.argument("name")
def kubeconfig(name: str) -> None:
    click.echo(str(environment_kubeconfig(name)))


@click.group(help="Resolve and build Distribution application charts")
def distribution() -> None:
    pass


@distribution.command("build")
@click.option(
    "--distribution",
    "path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
def build(path: Path) -> None:
    build_distribution(
        load_distribution(path), ChartResolver(progress=click.echo), click.echo
    )
    click.echo("Distribution charts ready")


@click.group("images", help="List and archive images for named Environments")
def images_group() -> None:
    pass


@images_group.command("list")
@click.option("--environment", "name", required=True)
@click.option(
    "--include", "includes", multiple=True, help="Image reference glob; repeatable"
)
def list_images(name: str, includes: tuple[str, ...]) -> None:
    for ref in images.list_images(require_environment(name), includes):
        click.echo(ref)


@images_group.command("dump")
@click.option("--environment", "name", required=True)
@click.option(
    "--output", required=True, type=click.Path(dir_okay=False, path_type=Path)
)
@click.option(
    "--include", "includes", multiple=True, help="Image reference glob; repeatable"
)
def dump_images(name: str, output: Path, includes: tuple[str, ...]) -> None:
    images.dump_images(require_environment(name), output, includes)


@images_group.command("load")
@click.option("--environment", "name", required=True)
@click.option(
    "--archive", required=True, type=click.Path(dir_okay=False, path_type=Path)
)
def load_images(name: str, archive: Path) -> None:
    images.load_images(require_environment(name), archive)


@images_group.command("pack")
@click.option(
    "--helm-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--output", required=True, type=click.Path(dir_okay=False, path_type=Path)
)
def pack(helm_dir: Path, output: Path) -> None:
    pack_images(helm_dir.resolve(), output)


@click.group("secrets", help="Manage Kubernetes Secrets in a named Environment")
def secrets_group() -> None:
    pass


@secrets_group.command("create")
@click.option("--environment", "name", required=True)
@click.option("--namespace", required=True)
@click.option(
    "--ci-secrets-file", type=click.Path(exists=True, dir_okay=False, path_type=Path)
)
def create_secrets(name: str, namespace: str, ci_secrets_file: Path | None) -> None:
    target = require_environment(name)
    if ci_secrets_file is not None:
        secrets.create_additional_secrets(target, namespace, ci_secrets_file)
    secrets.create_image_pull_secret(target, namespace)


@click.group(
    "terraform", help="Manage standalone Terraform resources in a named Environment"
)
def terraform_group() -> None:
    pass


@terraform_group.command("apply")
@click.option("--environment", "name", required=True)
@click.option("--root", required=True, type=click.Path(path_type=Path))
@click.option("--namespace", required=True)
def terraform_apply(name: str, root: Path, namespace: str) -> None:
    terraform.apply_terraform(require_environment(name), root, namespace)


@terraform_group.command("destroy")
@click.option("--environment", "name", required=True)
@click.option("--root", required=True, type=click.Path(path_type=Path))
@click.option("--namespace", required=True)
def terraform_destroy(name: str, root: Path, namespace: str) -> None:
    terraform.destroy_terraform(require_environment(name), root, namespace)
