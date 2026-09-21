from pathlib import Path

import click

from zep_dev import cluster_images
from zep_dev.commands.cluster.create import create
from zep_dev.commands.cluster.debug_dump import debug_dump
from zep_dev.commands.cluster.teardown import teardown


@click.group("cluster", help="Manage the local kind cluster")
def cluster() -> None:
    pass


@cluster.group("images", help="Save and load images from the local kind cluster")
def images() -> None:
    pass


@images.command("list")
@click.option(
    "--include",
    "includes",
    multiple=True,
    help="Only include image references matching this glob; repeatable",
)
def list_images(includes: tuple[str, ...]) -> None:
    engine = cluster_images.choose_engine()
    for ref in cluster_images.discover_image_refs(engine, includes):
        click.echo(ref)


@images.command("dump")
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the image archive here",
)
@click.option(
    "--include",
    "includes",
    multiple=True,
    help="Only include image references matching this glob; repeatable",
)
def dump_images(output: Path, includes: tuple[str, ...]) -> None:
    cluster_images.dump_images(output, includes)


@images.command("pack")
@click.option(
    "--helm-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Root directory containing ct.yaml and application charts",
)
@click.argument(
    "application_paths",
    nargs=-1,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--ref",
    "refs",
    multiple=True,
    help="Map an Application value-file ref to a local root as NAME=PATH; repeatable",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the image archive here",
)
def pack_images(
    helm_dir: Path | None,
    application_paths: tuple[Path, ...],
    refs: tuple[str, ...],
    output: Path,
) -> None:
    if helm_dir is not None:
        if application_paths:
            raise click.UsageError(
                "--helm-dir cannot be combined with Application paths"
            )
        if refs:
            raise click.UsageError("--ref can only be used with Application paths")
        cluster_images.pack_images(helm_dir.resolve(), output)
        return

    if not application_paths:
        raise click.UsageError("provide --helm-dir or one or more Application paths")

    cluster_images.pack_applications(application_paths, refs, output)


@images.command("load")
@click.option(
    "--archive",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Load images from this archive",
)
def load_images(archive: Path) -> None:
    cluster_images.load_images(archive)


cluster.add_command(create)
cluster.add_command(teardown)
cluster.add_command(debug_dump)
