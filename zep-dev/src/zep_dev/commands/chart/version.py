"""Chart-version CLI command."""

import click

from zep_dev.chart_version import calculate_chart_version


@click.command("version")
def version() -> None:
    click.echo(calculate_chart_version())
