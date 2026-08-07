import click

from zep_dev.k8s_secrets import create_image_pull_secret


@click.command("create")
@click.option(
    "--namespace",
    required=True,
    help="Namespace in which to create the github-registry image-pull Secret",
)
def create(namespace: str) -> None:
    create_image_pull_secret(namespace)
