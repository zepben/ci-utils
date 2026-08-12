import json
from pathlib import Path

import click
from pydantic.dataclasses import dataclass

from zep_dev.models import ChartMetadata


@dataclass
class KeyValue:
    key: str
    value: str


def parse_key_value(
    ctx: click.Context,
    param: click.Parameter,
    value: str | None,
) -> KeyValue | None:
    if value is None:
        return None
    key, sep, val = value.partition("=")
    if not sep or not key or not val:
        raise click.BadParameter(
            "must be in KEY=VALUE form with a non-empty key and value",
            ctx=ctx,
            param=param,
        )
    return KeyValue(key, val)


@click.command("list")
@click.option(
    "--helm-dir",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    required=True,
)
@click.option("--annotation", callback=parse_key_value)
@click.option("--type", "chart_type")
def list_charts(
    helm_dir: Path,
    annotation: KeyValue | None,
    chart_type: str | None,
) -> None:
    """List Helm charts selected by Chart.yaml metadata."""

    matches: list[str] = []
    for chart_yaml in sorted((helm_dir / "charts").glob("*/Chart.yaml")):
        chart_dir = chart_yaml.parent
        metadata = ChartMetadata.from_chart_dir(chart_dir)
        if (
            annotation is not None
            and metadata.annotations.get(annotation.key) != annotation.value
        ):
            continue
        if chart_type is not None and metadata.type != chart_type:
            continue
        matches.append(str(chart_dir))

    click.echo(json.dumps(matches))
