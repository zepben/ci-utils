import logging
import os

import click

from local_k8s.groups.chart import chart
from local_k8s.groups.cluster import cluster
from local_k8s.groups.tools import tools
from local_k8s.shared import get_bin_dir


@click.group(help="Manage a local kind cluster for chart testing")
@click.option(
    "-v", "--verbose", count=True, help="Increase log verbosity (-v=INFO, -vv=DEBUG)"
)
def cli(verbose: int) -> None:
    add_bin_dir_to_path()
    configure_logging(verbose)


def add_bin_dir_to_path() -> None:
    # We need to add our bin dir at the start of path to be sure
    # we always resolve our installed tools and not whatever is
    # in the user's env.
    bin_dir = str(get_bin_dir().resolve())
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{path}"


def configure_logging(verbose: int) -> None:
    if verbose == 0:
        level = logging.WARNING
    elif verbose == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG
    logging.basicConfig(level=level)


cli.add_command(cluster)
cli.add_command(tools)
cli.add_command(chart)
