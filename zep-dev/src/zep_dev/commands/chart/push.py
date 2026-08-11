from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory

import click
from click import ClickException
from pydantic import ValidationError

from zep_dev.commands.chart.utils import validate_dependencies_present
from zep_dev.models import ChartMetadata, ChartTestingConfig
from zep_dev.shared import execute
from zep_dev.static import CT_YAML

REGISTRY_HOST = "ghcr.io"


def _detailed_failure_for(step: str, e: CalledProcessError) -> ClickException:
    stdout = e.output if isinstance(e.output, str) else ""
    msg = f"{step} failed with rc={e.returncode}"
    if stdout.strip():
        msg = f"{msg}\n{stdout.strip()}"
    return ClickException(msg)


@click.command("push")
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
    "--registry-config",
    type=click.Path(
        exists=True,
        file_okay=True,
        dir_okay=False,
        path_type=Path,
    ),
    required=True,
)
@click.option("--oci-repo", required=True, help="OCI path after host, e.g. owner/repo")
def push(
    chart: Path,
    registry_config: Path,
    oci_repo: str,
) -> None:
    chart = chart.resolve()
    try:
        meta = ChartMetadata.from_chart_dir(chart)
    except (ValueError, ValidationError) as e:
        raise ClickException(str(e)) from e

    version = meta.version

    oci_base = f"oci://{REGISTRY_HOST}/{oci_repo}"
    oci_chart = f"{oci_base}/{meta.name}"
    archive_name = f"{meta.name}-{version}.tgz"
    registry_config_arg = str(registry_config)

    result = execute(
        "helm",
        "show",
        "chart",
        oci_chart,
        "--version",
        version,
        "--registry-config",
        registry_config_arg,
        check=False,
        capture_stdout=True,
        capture_stderr=True,
    )
    if result.returncode == 0:
        click.echo(
            f"{meta.name}:{version} already exists in registry, skipping push",
            err=True,
        )
        return

    text = f"{result.stderr}\n{result.stdout}".lower()
    if "not found" not in text and "manifest unknown" not in text:
        raise ClickException(
            f"exist check failed (rc={result.returncode}): {result.stderr.strip()}"
        )

    # We count on our standard structure being:
    # helm -> charts -> chart-name
    helm_dir = chart.parent.parent
    ct_path = helm_dir / CT_YAML
    ct_config = ChartTestingConfig.from_chart_dir(helm_dir)
    validate_dependencies_present(meta, ct_config, ct_path)

    try:
        for repo in ct_config.chart_repos:
            name, url = repo.split("=", 1)
            # OCI repos don't need to be explicitly added in the same way
            # as HTTPS ones.
            if url.startswith("oci://"):
                continue
            execute(
                "helm",
                "repo",
                "add",
                name,
                url,
                "--force-update",
                capture_stdout=True,
            )
    except CalledProcessError as e:
        raise _detailed_failure_for("repository setup", e) from e

    try:
        execute(
            "helm",
            "dependency",
            "build",
            str(chart),
            "--registry-config",
            registry_config_arg,
            capture_stdout=True,
        )
    except CalledProcessError as e:
        raise _detailed_failure_for("dependency build", e) from e

    with TemporaryDirectory() as tmp:
        try:
            execute(
                "helm",
                "package",
                str(chart),
                "--destination",
                tmp,
                capture_stdout=True,
            )
            execute(
                "helm",
                "push",
                str(Path(tmp) / archive_name),
                oci_base,
                "--registry-config",
                registry_config_arg,
                capture_stdout=True,
            )
        except CalledProcessError as e:
            raise _detailed_failure_for("push", e) from e
