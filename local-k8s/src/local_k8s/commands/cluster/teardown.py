import click

from local_k8s import cluster


@click.command("teardown")
def teardown() -> None:
    cluster.teardown_cluster()
