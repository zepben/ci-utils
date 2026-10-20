import os
from pathlib import Path

import click

from zep_dev.ci import prepare_image_archive


@click.group(help="Prepare CI resources")
def ci() -> None:
    pass


@ci.command("prepare-image-archive")
@click.option(
    "--config",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Discovery YAML; paths and Application globs are relative to this file",
)
@click.option("--repository", envvar="GITHUB_REPOSITORY", required=True)
@click.option("--run-id", envvar="GITHUB_RUN_ID", required=True, type=int)
@click.option("--bundle", default="kind-images-v1", show_default=True)
def prepare_archive(
    config: Path,
    repository: str,
    run_id: int,
    bundle: str,
) -> None:
    outputs = prepare_image_archive(
        config, repository, run_id, bundle, Path(os.environ["RUNNER_TEMP"])
    )
    for key, value in outputs.items():
        click.echo(f"{key}={value}")
