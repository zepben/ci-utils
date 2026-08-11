import json
from pathlib import Path

import click

from zep_dev.commands.chart.utils import calculate_chart_version
from zep_dev.models import ChartMetadata, ChartValues


@click.group("metadata")
def metadata() -> None:
    """Show or update Helm chart metadata."""


@metadata.command("show")
@click.option(
    "--chart",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    required=True,
)
def show(chart: Path) -> None:
    meta = ChartMetadata.from_chart_dir(chart)
    click.echo(json.dumps(meta.model_dump(mode="json")))


@metadata.command(
    "update",
    help="Update Chart.yaml with calculated version, and values.yaml with --image-tag, if passed",
)
@click.option(
    "--chart",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    required=True,
)
@click.option(
    "--image-tag",
    default="",
    help="Docker image tag to write to values.yaml image.tag. Can be empty, which results in values.yaml update being skipped",
)
def update(chart: Path, image_tag: str) -> None:
    """Set finalized release metadata in a chart directory."""
    chart_metadata = ChartMetadata.from_chart_dir(chart)
    release_version = calculate_chart_version()

    chart_metadata.version = release_version
    chart_metadata.appVersion = release_version

    if not image_tag.strip():
        chart_metadata.write(chart)
        click.echo("--image-tag empty, not updating values.yaml")
        return

    values = ChartValues.from_chart_dir(chart)
    values.image.tag = image_tag

    chart_metadata.write(chart)
    values.write(chart)
