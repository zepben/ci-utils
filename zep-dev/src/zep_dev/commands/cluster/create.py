from pathlib import Path

import click

from zep_dev import cluster
from zep_dev.k8s import KUBECONF_PATH
from zep_dev.models import LOCAL_REPO_MOUNT_ROOT, ClusterComponents


@click.command("create")
@click.option(
    "--kind-config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to kind cluster config YAML",
)
@click.option(
    "--components",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--local-repo",
    "local_repos",
    multiple=True,
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    help=(
        "Local Git repository to bind-mount into kind workers at "
        f"{LOCAL_REPO_MOUNT_ROOT}/<basename>. Repeatable."
    ),
)
def create(
    kind_config: Path,
    components: Path,
    local_repos: tuple[Path, ...],
) -> None:
    cluster.create_cluster(
        kind_config,
        components=ClusterComponents.from_path(components),
        local_repos=local_repos,
    )
    click.echo("Cluster created. Execute:")
    click.echo(f"    export KUBECONFIG={KUBECONF_PATH}")
    click.echo("To interact with kubectl/helm")
