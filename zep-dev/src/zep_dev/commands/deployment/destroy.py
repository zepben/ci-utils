from pathlib import Path

import click
from click import echo

from zep_dev import cluster
from zep_dev.profile import load_profile_metadata
from zep_dev.terraform_roots import discard_profile_terraform


@click.command("destroy")
@click.option(
    "--profile",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help=(
        "Path to Profile YAML. metadata.name is always read. "
        "Deletes the named Kind cluster, then discards its local Terraform "
        "files and state (Distribution need not load)."
    ),
)
def destroy(profile: Path) -> None:
    metadata = load_profile_metadata(profile)
    echo(f"Deleting Kind cluster {metadata.name!r}")
    cluster.teardown_cluster(cluster_name=metadata.name)
    discard_profile_terraform(metadata.name)
