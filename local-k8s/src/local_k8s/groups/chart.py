import click

from local_k8s.commands.chart.metadata import metadata


@click.group("chart", help="Helm chart lint, test, and publish commands")
def chart() -> None:
    pass


chart.add_command(metadata)
