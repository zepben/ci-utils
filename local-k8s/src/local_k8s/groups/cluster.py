import click

from local_k8s.commands.cluster.create import create
from local_k8s.commands.cluster.debug_dump import debug_dump
from local_k8s.commands.cluster.teardown import teardown


@click.group("cluster", help="Manage the local kind cluster")
def cluster() -> None:
    pass


cluster.add_command(create)
cluster.add_command(teardown)
cluster.add_command(debug_dump)
