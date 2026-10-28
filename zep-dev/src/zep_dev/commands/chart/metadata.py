import json
from pathlib import Path

import click

from zep_dev.chart_version import calculate_chart_version
from zep_dev.models import ChartMetadata, ChartValues
from zep_dev.runtime_contract import (
    RUNTIME_CONTRACT_REF_ANNOTATION,
    runtime_contract_ref,
)

# When this annotation is present and set to true, it indicates that we
# should process the metadata update and update the version/tag.
PUBLISH_ANNOTATION = "zepben.com/publish-with-application-image"


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
    help="Update release metadata according to the chart annotations",
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
    help="Docker image tag for charts published with the application image",
)
def update(chart: Path, image_tag: str) -> None:
    """Set finalized release metadata in a chart directory."""
    chart_metadata = ChartMetadata.from_chart_dir(chart)
    publish_with_image = chart_metadata.annotations.get(PUBLISH_ANNOTATION) == "true"
    image_tag = image_tag.strip()

    values: ChartValues | None = None
    if publish_with_image:
        if not image_tag:
            raise click.ClickException(
                "--image-tag is required for charts published with the application image"
            )
        if chart_metadata.type != "application":
            raise click.ClickException(
                "charts published with the application image must have type application"
            )
        if not (chart / "values.yaml").is_file():
            raise click.ClickException(
                "values.yaml is required for charts published with the application image"
            )
        values = ChartValues.from_chart_dir(chart)
        if "tag" not in values.image.model_fields_set:
            raise click.ClickException(
                "values.yaml must define image.tag for charts published with the application image"
            )
    elif image_tag:
        raise click.ClickException(f"--image-tag requires the {PUBLISH_ANNOTATION}")

    try:
        contract_ref = runtime_contract_ref(chart)
    except ValueError as error:
        raise click.ClickException(str(error)) from error

    release_version = calculate_chart_version()
    chart_metadata.version = release_version
    chart_metadata.appVersion = release_version
    if contract_ref is not None:
        # Assign, not mutate: write() keeps only fields that were set.
        chart_metadata.annotations = {
            **chart_metadata.annotations,
            RUNTIME_CONTRACT_REF_ANNOTATION: contract_ref,
        }
    if values is not None:
        values.image.tag = image_tag

    chart_metadata.write(chart)
    if values is not None:
        values.write(chart)
