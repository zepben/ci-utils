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
