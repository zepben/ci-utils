from pathlib import Path

import click

from zep_dev import cluster_images
from zep_dev.commands.cluster.create import create
from zep_dev.commands.cluster.debug_dump import debug_dump
from zep_dev.commands.cluster.teardown import teardown
from zep_dev.models import ClusterComponents, ImageDiscoveryConfig


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
    "--config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Discovery YAML; paths and Application globs are relative to this file",
)
@click.option(
    "--helm-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Root directory containing ct.yaml and application charts",
)
@click.option(
    "--components",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Cluster components YAML containing bootstrap Helm charts",
)
@click.option(
    "--application",
    "applications",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Argo Application YAML to discover images from; repeatable",
)
@click.option(
    "--repository",
    "repositories",
    multiple=True,
    help="Map a Git source URL to an existing local checkout: URL=PATH; repeatable",
)
@click.option(
    "--list-only",
    is_flag=True,
    help="Print packable image references without pulling or saving images",
)
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Write the image archive here (required unless --list-only)",
)
def pack_images(
    config: Path | None,
    helm_dir: Path | None,
    components: Path | None,
    applications: tuple[Path, ...],
    repositories: tuple[str, ...],
    list_only: bool,
    output: Path | None,
) -> None:
    if config is not None:
        if (
            helm_dir is not None
            or components is not None
            or applications
            or repositories
        ):
            raise click.UsageError("--config cannot be combined with discovery options")
        discovery = ImageDiscoveryConfig.from_path(config)
        helm_dir, components = discovery.helm_dir, discovery.components
        applications = tuple(discovery.applications)
        mappings = discovery.repositories
    else:
        mappings = cluster_images.parse_repository_mappings(repositories)
    if helm_dir is None and components is None and not applications:
        raise click.UsageError(
            "at least one of --helm-dir, --components or --application is required"
        )
    if not list_only and output is None:
        raise click.UsageError("--output is required unless --list-only is used")
    source = ClusterComponents.from_path(components) if components is not None else None
    chart_dir = helm_dir.resolve() if helm_dir is not None else None
    if list_only:
        for ref in cluster_images.discover_pack_image_refs(
            chart_dir, source, applications, mappings
        ):
            click.echo(ref)
    else:
        assert output is not None
        cluster_images.pack_images(chart_dir, output, source, applications, mappings)


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
