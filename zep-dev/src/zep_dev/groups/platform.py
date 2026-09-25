import click

from zep_dev.commands.platform.apply import apply
from zep_dev.commands.platform.destroy import destroy


@click.group("platform", help="Apply and destroy multi-app Kind environments")
def platform() -> None:
    pass


platform.add_command(apply)
platform.add_command(destroy)
