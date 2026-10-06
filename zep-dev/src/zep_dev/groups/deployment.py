import click

from zep_dev.commands.deployment.apply import apply
from zep_dev.commands.deployment.destroy import destroy


@click.group("deployment", help="Apply and destroy multi-app Kind deployments")
def deployment() -> None:
    pass


deployment.add_command(apply)
deployment.add_command(destroy)
