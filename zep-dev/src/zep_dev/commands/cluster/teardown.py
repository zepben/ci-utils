import click

from zep_dev import cluster


@click.command("teardown")
def teardown() -> None:
    cluster.teardown_cluster()
