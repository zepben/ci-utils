import click

from zep_dev.commands.cluster.create import create
from zep_dev.commands.cluster.debug_dump import debug_dump
from zep_dev.commands.cluster.teardown import teardown


@click.group("cluster", help="Manage the local kind cluster")
def cluster() -> None:
    pass


cluster.add_command(create)
cluster.add_command(teardown)
cluster.add_command(debug_dump)
