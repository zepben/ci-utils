import click

from zep_dev.commands.distribution.build import build


@click.group("distribution", help="Work with application chart distributions")
def distribution() -> None:
    pass


distribution.add_command(build)
