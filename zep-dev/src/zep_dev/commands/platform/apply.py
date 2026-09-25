from pathlib import Path

import click

from zep_dev.distribution import Profile
from zep_dev.k8s import KUBECONF_PATH
from zep_dev.platform import apply_profile


@click.command("apply")
@click.option(
    "--profile",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to Profile YAML (resolves nested Distribution).",
)
@click.option(
    "--allow-reuse",
    is_flag=True,
    default=False,
    help=(
        "If a Kind cluster named metadata.name already exists, reuse it "
        "instead of failing. Intended for local iteration; Kind config and "
        "Helm state may not match the Profile."
    ),
)
@click.option(
    "--image-archive",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Load images from this archive after Kind is up, before installing components",
)
def apply(profile: Path, allow_reuse: bool, image_archive: Path | None) -> None:
    loaded = Profile.from_path(profile)
    apply_profile(loaded, allow_reuse=allow_reuse, image_archive=image_archive)
    click.echo("Platform applied. Execute:")
    click.echo(f"    export KUBECONFIG={KUBECONF_PATH}")
    click.echo("To interact with kubectl/helm")
