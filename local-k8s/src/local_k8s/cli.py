import logging

import click

from local_k8s.groups.cluster import cluster
from local_k8s.groups.tools import tools


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


cli.add_command(cluster)
cli.add_command(tools)
