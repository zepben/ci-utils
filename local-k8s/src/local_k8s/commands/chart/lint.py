from contextlib import chdir
from pathlib import Path
from subprocess import CalledProcessError

import click
from click import ClickException

from local_k8s.shared import execute, resolve_chart
from local_k8s.static import CT_YAML


@click.command("lint")
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
@click.option(
    "--chart",
    type=click.Path(
        exists=False,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    required=True,
)
def lint(helm_dir: Path, chart: Path) -> None:
    helm_dir = helm_dir.resolve()
    if not (helm_dir / CT_YAML).is_file():
        raise ClickException(f"{CT_YAML} is required in the root of --helm-dir")

    resolved_chart = resolve_chart(helm_dir, chart)

    with chdir(helm_dir):
        try:
            execute(
                "ct",
                "lint",
                "--config",
                str(CT_YAML),
                "--charts",
                str(resolved_chart.path_relative_to_helm_dir),
                "--check-version-increment=true",
            )
        except CalledProcessError as e:
            raise ClickException(f"lint failed with rc={e.returncode}") from e
