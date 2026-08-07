from contextlib import chdir
from pathlib import Path
from subprocess import CalledProcessError

import click
from click import ClickException

from zep_dev.models import ChartMetadata, ChartTestingConfig
from zep_dev.shared import ResolvedChart, execute, resolve_chart
from zep_dev.static import CT_YAML

KUBERNETES_VERSION = "1.35.0"
DATREE_CRD_SCHEMA_LOCATION = (
    "https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/"
    "{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
)


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
        run_chart_testing_lint(resolved_chart)
        validate_chart_manifests(resolved_chart, chart_metadata)


def run_chart_testing_lint(resolved_chart: ResolvedChart) -> None:
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


def validate_chart_manifests(
    resolved_chart: ResolvedChart, chart_metadata: ChartMetadata
) -> None:
    if chart_metadata.type == "library":
        click.echo(f"Skipping kubeconform for library chart: {chart_metadata.name}")
        return
    helm_args = [
        "helm",
        "template",
        chart_metadata.name,
        str(resolved_chart.path_relative_to_helm_dir),
        "--kube-version",
        KUBERNETES_VERSION,
        "--include-crds",
    ]
    values_files = [
        path.relative_to(resolved_chart.absolute_path)
        for path in sorted(resolved_chart.absolute_path.glob("ci/*-values.yaml"))
    ]
    if not values_files:
        execute_kubeconform(helm_args, "chart defaults")
    else:
        for values_file in values_files:
            values_path = resolved_chart.path_relative_to_helm_dir / values_file
            execute_kubeconform(
                [*helm_args, "--values", str(values_path)], str(values_path)
            )


def execute_kubeconform(helm_args: list[str], variant: str) -> None:
    click.echo(f"Validating Kubernetes schemas for {variant}")
    try:
        rendered = execute(*helm_args, capture_stdout=True)
    except CalledProcessError as e:
        raise ClickException(
            f"helm template failed for {variant} with rc={e.returncode}"
        ) from e

    try:
        execute(
            "kubeconform",
            "-kubernetes-version",
            KUBERNETES_VERSION,
            "-strict",
            "-ignore-missing-schemas",
            "-schema-location",
            "default",
            "-schema-location",
            DATREE_CRD_SCHEMA_LOCATION,
            "-summary",
            input=rendered.stdout,
        )
    except CalledProcessError as e:
        raise ClickException(
            f"kubeconform failed for {variant} with rc={e.returncode}"
        ) from e


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
