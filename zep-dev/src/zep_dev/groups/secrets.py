import click

from zep_dev.commands.secrets.create import create


@click.group("secrets", help="Manage Kubernetes Secrets for local kind testing")
def secrets() -> None:
    pass


secrets.add_command(create)
