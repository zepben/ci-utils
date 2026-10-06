from pathlib import Path

import click

from zep_dev import cluster_images
from zep_dev.cluster import CLUSTER_NAME
from zep_dev.commands.cluster.create import create
from zep_dev.commands.cluster.debug_dump import debug_dump
from zep_dev.commands.cluster.teardown import teardown


@click.group("cluster", help="Manage the local kind cluster")
def cluster() -> None:
    pass


@cluster.group("images", help="Save and load images from the local kind cluster")
@click.option(
    "--cluster-name",
    default=CLUSTER_NAME,
    show_default=True,
    help="Kind cluster name",
)
@click.pass_context
def images(ctx: click.Context, cluster_name: str) -> None:
    ctx.ensure_object(dict)
    ctx.obj["cluster_name"] = cluster_name


@images.command("list")
@click.option(
    "--include",
    "includes",
    multiple=True,
    help="Only include image references matching this glob; repeatable",
)
@click.pass_context
def list_images(ctx: click.Context, includes: tuple[str, ...]) -> None:
    engine = cluster_images.choose_engine()
    for ref in cluster_images.discover_image_refs(
        engine, includes, cluster_name=ctx.obj["cluster_name"]
    ):
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
@click.pass_context
def dump_images(ctx: click.Context, output: Path, includes: tuple[str, ...]) -> None:
    cluster_images.dump_images(output, includes, cluster_name=ctx.obj["cluster_name"])


@images.command("pack")
@click.option(
    "--helm-dir",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Root directory containing ct.yaml and application charts",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the image archive here",
)
def pack_images(helm_dir: Path, output: Path) -> None:
    cluster_images.pack_images(
        helm_dir.resolve(),
        output,
    )


@images.command("load")
@click.option(
    "--archive",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Load images from this archive",
)
@click.pass_context
def load_images(ctx: click.Context, archive: Path) -> None:
    cluster_images.load_images(archive, cluster_name=ctx.obj["cluster_name"])


cluster.add_command(create)
cluster.add_command(teardown)
cluster.add_command(debug_dump)
