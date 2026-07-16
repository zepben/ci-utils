import json
from pathlib import Path

import click
from click import ClickException
from pydantic import ValidationError

from local_k8s.models import ChartMetadata


@click.command("metadata")
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
def metadata(chart: Path) -> None:
    try:
        meta = ChartMetadata.from_chart_dir(chart)
    except (ValueError, ValidationError) as e:
        raise ClickException(str(e)) from e
    click.echo(json.dumps(meta.model_dump(mode="json")))
