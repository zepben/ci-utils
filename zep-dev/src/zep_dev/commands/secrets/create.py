from pathlib import Path

import click

from zep_dev.k8s_secrets import create_additional_secrets, create_image_pull_secret


@click.command("create")
@click.option(
    "--namespace",
    required=True,
    help="Namespace in which to create the github-registry image-pull Secret",
)
@click.option(
    "--ci-secrets-file",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
def create(namespace: str, ci_secrets_file: Path | None) -> None:
    if ci_secrets_file is not None:
        create_additional_secrets(namespace, ci_secrets_file)
    create_image_pull_secret(namespace)
