import logging
import os

import click

from zep_dev.groups.chart import chart
from zep_dev.groups.cluster import cluster
from zep_dev.groups.secrets import secrets
from zep_dev.groups.terraform import terraform
from zep_dev.groups.tools import tools
from zep_dev.shared import get_bin_dir, resolve_registry_config

LOG = logging.getLogger(__name__)


@click.group(help="Manage a local kind cluster for chart testing")
@click.option(
    "-v", "--verbose", count=True, help="Increase log verbosity (-v=INFO, -vv=DEBUG)"
)
def cli(verbose: int) -> None:
    configure_logging(verbose)
    add_bin_dir_to_path()
    configure_helm_registry()


def add_bin_dir_to_path() -> None:
    # We need to add our bin dir at the start of path to be sure
    # we always resolve our installed tools and not whatever is
    # in the user's env.
    bin_dir = str(get_bin_dir().resolve())
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{path}"


def configure_helm_registry() -> None:
    if "HELM_REGISTRY_CONFIG" in os.environ:
        return
    # Helm uses it's own standard location for the registry by default. The structure is
    # exactly the same as the docker/podman registry config, so just locate and use it directly
    # instead of requiring people to duplicate the file. It is implemented as an env var so that
    # child processes (like ct) can inherit the same config.
    registry_config = resolve_registry_config()
    if registry_config is not None:
        LOG.debug("Setting registry config: HELM_REGISTRY_CONFIG=%s", registry_config)
        os.environ["HELM_REGISTRY_CONFIG"] = str(registry_config)


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
cli.add_command(secrets)
cli.add_command(terraform)
