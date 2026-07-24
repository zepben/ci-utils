from contextlib import chdir
from pathlib import Path
from subprocess import CalledProcessError

import click
from click import ClickException

from local_k8s.models import ChartMetadata, ChartTestingConfig
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
    ct_path = helm_dir / CT_YAML
    if not ct_path.is_file():
        raise ClickException(f"{CT_YAML} is required in the root of --helm-dir")

    resolved_chart = resolve_chart(helm_dir, chart)
    ct_config = ChartTestingConfig.from_chart_dir(helm_dir)
    chart_metadata = ChartMetadata.from_chart_dir(resolved_chart.absolute_path)
    validate_dependencies_present(chart_metadata, ct_config, ct_path)
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


def validate_dependencies_present(
    chart_metadata: ChartMetadata, ct_config: ChartTestingConfig, ct_path: Path
) -> None:
    # Syntax is <name>=<url>
    chart_repos = [repo.split("=")[-1] for repo in ct_config.chart_repos]
    for dependency in chart_metadata.dependencies:
        # helm pulls OCI deps from the url in Chart.yaml during dependency build without helm repo add,
        # so no need for us to validate it's existence in chart repos.
        if dependency.repository.startswith("oci://ghcr.io"):
            continue
        if dependency.repository not in chart_repos:
            raise ClickException(
                f"{dependency.repository} not found in {ct_path}. It needs to be added under the chart_repos list, in the format <name>=<url>"
            )
