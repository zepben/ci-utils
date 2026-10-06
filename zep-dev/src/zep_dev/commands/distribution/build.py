from pathlib import Path

import click

from zep_dev.chart_artifacts import ChartResolver
from zep_dev.distribution import Distribution, ordered_charts


@click.command("build")
@click.option(
    "--distribution",
    "distribution_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to Distribution YAML.",
)
def build(distribution_path: Path) -> None:
    distribution = Distribution.from_path(distribution_path)
    resolver = ChartResolver()
    for name, locator in ordered_charts(distribution.charts):
        click.echo(f"Processing {name}")
        resolver.ensure(resolver.resolve(name, locator))
    click.echo("Distribution charts ready")
