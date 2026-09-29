from contextlib import chdir
from pathlib import Path
from subprocess import CalledProcessError

import click
import yaml
from click import ClickException
from pydantic import ValidationError

from zep_dev.commands.chart.utils import discover_charts, execute_ct_lint
from zep_dev.k8s import kubectl, resource_exists
from zep_dev.k8s_secrets import create_additional_secrets, create_image_pull_secret
from zep_dev.models import ChartMetadata
from zep_dev.shared import (
    ResolvedChart,
    resolve_chart,
)
from zep_dev.static import CI_SECRETS_YAML, CT_YAML


@click.command("test")
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
    default=None,
)
def test(helm_dir: Path, chart: Path | None) -> None:
    helm_dir = helm_dir.resolve()
    if not (helm_dir / CT_YAML).is_file():
        raise ClickException(f"{CT_YAML} is required in the root of --helm-dir")

    if chart is not None:
        resolved_charts = [resolve_chart(helm_dir, chart)]
    else:
        resolved_charts = [
            ResolvedChart(
                absolute_path=helm_dir / discovered_chart,
                path_relative_to_helm_dir=discovered_chart,
            )
            for discovered_chart in discover_charts(helm_dir)
        ]

    with chdir(helm_dir):
        namespace = create_test_namespace(CT_YAML)
        create_secrets(namespace=namespace)

        for resolved_chart in resolved_charts:
            test_chart(resolved_chart)


def test_chart(resolved_chart: ResolvedChart) -> None:
    try:
        meta = ChartMetadata.from_chart_dir(resolved_chart.absolute_path)
    except (ValueError, ValidationError) as e:
        raise ClickException(str(e)) from e

    if meta.type == "library":
        click.echo(f"Skipping install for library chart: {meta.name}")
        return

    execute_lint_and_install(CT_YAML, resolved_chart.path_relative_to_helm_dir)


def create_test_namespace(ct_yaml_path: Path) -> str:
    ct_yaml = yaml.safe_load(ct_yaml_path.read_text())
    test_namespace: str | None = ct_yaml.get("namespace")
    if test_namespace is None:
        raise ClickException(f"namespace must be specified in {CT_YAML}")
    if not resource_exists("namespace", test_namespace):
        kubectl("create", "namespace", test_namespace)
    return test_namespace


def create_secrets(namespace: str) -> None:
    if CI_SECRETS_YAML.exists():
        create_additional_secrets(namespace, CI_SECRETS_YAML)
    create_image_pull_secret(namespace)


def execute_lint_and_install(
    ct_yaml_path: Path, chart_path_relative_to_helm_dir: Path
) -> None:
    try:
        execute_ct_lint(
            "lint-and-install",
            "--config",
            str(ct_yaml_path),
            "--charts",
            str(chart_path_relative_to_helm_dir),
            "--check-version-increment=true",
        )
    except CalledProcessError as e:
        raise ClickException(f"lint-and-install failed with rc={e.returncode}") from e
