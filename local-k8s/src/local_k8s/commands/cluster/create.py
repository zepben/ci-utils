from io import TextIOWrapper
from pathlib import Path

import click

from local_k8s import cluster
from local_k8s.cluster import KUBECONF_PATH
from local_k8s.models import ClusterComponents


@click.command("create")
@click.option(
    "--kind-config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to kind cluster config YAML",
)
@click.option("--components", type=click.File("r"), required=True)
def create(kind_config: Path, components: TextIOWrapper) -> None:
    cluster.create_cluster(
        kind_config,
        components=ClusterComponents.from_text_io(components),
    )
    click.echo("Cluster created. Execute:")
    click.echo(f"    export KUBECONFIG={KUBECONF_PATH}")
    click.echo("To interact with kubectl/helm")
