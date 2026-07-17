import json
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory

import click
from click import ClickException
from pydantic import ValidationError

from local_k8s.models import ChartMetadata
from local_k8s.shared import execute

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
@click.option("--beta", default=None)
@click.option("--fail-if-exists", is_flag=True, default=False)
def push(
    chart: Path,
    registry_config: Path,
    oci_repo: str,
    beta: str | None,
    fail_if_exists: bool,
) -> None:
    try:
        meta = ChartMetadata.from_chart_dir(chart)
    except (ValueError, ValidationError) as e:
        raise ClickException(str(e)) from e

    version = f"{meta.version}-beta.{beta}" if beta is not None else meta.version

    oci_base = f"oci://{REGISTRY_HOST}/{oci_repo}"
    oci_chart = f"{oci_base}/{meta.name}"
    archive_name = f"{meta.name}-{version}.tgz"
    registry_config_arg = str(registry_config)

    if fail_if_exists:
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
            raise ClickException(f"{meta.name}:{version} already exists in registry")
        text = f"{result.stderr}\n{result.stdout}".lower()
        if "not found" not in text and "manifest unknown" not in text:
            raise ClickException(
                f"exist check failed (rc={result.returncode}): {result.stderr.strip()}"
            )

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
        package_args = [
            "helm",
            "package",
            str(chart),
            "--destination",
            tmp,
        ]
        if beta is not None:
            package_args.extend(["--version", version])
        try:
            execute(*package_args, capture_stdout=True)
            execute(
                "helm",
                "push",
                str(Path(tmp) / archive_name),
                oci_base,
                "--registry-config",
                registry_config_arg,
                capture_stdout=True,
            )
            execute(
                "helm",
                "show",
                "chart",
                oci_chart,
                "--version",
                version,
                "--registry-config",
                registry_config_arg,
                capture_stdout=True,
            )
        except CalledProcessError as e:
            raise _detailed_failure_for("push", e) from e

        click.echo(
            json.dumps(
                {
                    "name": meta.name,
                    "version": version,
                    "oci_ref": f"{REGISTRY_HOST}/{oci_repo}/{meta.name}:{version}",
                    "archive": archive_name,
                }
            )
        )
