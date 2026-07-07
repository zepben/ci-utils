import logging
from io import TextIOWrapper
from pathlib import Path

import click

from local_k8s import cluster
from local_k8s.cluster import KUBECONF_PATH
from local_k8s.models import ClusterComponents


@click.group(help="Manage a local kind cluster for chart testing")
@click.option(
    "-v", "--verbose", count=True, help="Increase log verbosity (-v=INFO, -vv=DEBUG)"
)
def cli(verbose: int) -> None:
    if verbose == 0:
        level = logging.WARNING
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(level=level)


@cli.command("create-cluster")
@click.option(
    "--kind-config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to kind cluster config YAML",
)
@click.option("--components", type=click.File("r"), required=True)
def create_cluster(kind_config: Path, components: TextIOWrapper) -> None:
    cluster.create_cluster(
        kind_config,
        components=ClusterComponents.from_text_io(components),
    )
    print("Cluster created. Execute:")
    print(f"    export KUBECONFIG={KUBECONF_PATH}")
    print("To interact with kubectl/helm")


@cli.command("teardown-cluster")
def teardown_cluster() -> None:
    cluster.teardown_cluster()


@click.option("--namespaces", multiple=True, help="Only dump these namespaces")
@click.option(
    "--out-dir",
    help="Write the dump here",
    type=click.Path(
        exists=True,
        dir_okay=True,
        file_okay=False,
        path_type=Path,
    ),
)
@cli.command("debug-dump")
def debug_dump(namespaces: list[str], out_dir: Path) -> None:
    cluster.take_debug_dump(filter_namespaces=namespaces, out_dir=out_dir)
