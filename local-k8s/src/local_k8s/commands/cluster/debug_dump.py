from pathlib import Path

import click

from local_k8s import cluster


@click.command("debug-dump")
@click.option("--namespaces", multiple=True, help="Only dump these namespaces")
@click.option(
    "--out-dir",
    help="Write the dump here",
    type=click.Path(
        exists=True,
        dir_okay=True,
        file_okay=False,
        path_type=Path,
    ),
)
def debug_dump(namespaces: list[str], out_dir: Path | None) -> None:
    cluster.take_debug_dump(filter_namespaces=namespaces, out_dir=out_dir)
