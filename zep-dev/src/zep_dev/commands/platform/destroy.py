from pathlib import Path

import click
from click import echo

from zep_dev import cluster
from zep_dev.distribution import load_profile_metadata
from zep_dev.platform import destroy_profile_terraform


@click.command("destroy")
@click.option(
    "--profile",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help=(
        "Path to Profile YAML. metadata.name is always read. "
        "Terraform destroy uses generated roots under /tmp/zep-dev-terraform "
        "when present (Distribution need not load)."
    ),
)
def destroy(profile: Path) -> None:
    metadata = load_profile_metadata(profile)
    echo(f"Destroying Terraform for profile {metadata.name!r} (if any)")
    destroy_profile_terraform(metadata.name)
    cluster.teardown_cluster(cluster_name=metadata.name)
