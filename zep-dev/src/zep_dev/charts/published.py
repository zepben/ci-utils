"""Read charts published to the zepben OCI chart repository."""

import tarfile
import tempfile
from pathlib import Path

import yaml

from zep_dev.models import ChartMetadata
from zep_dev.shared import execute

CHART_REPOSITORY = "ghcr.io/zepben/charts"
CHART_OCI_PREFIX = f"oci://{CHART_REPOSITORY}"
_PULL_TIMEOUT = 60


def published_chart_metadata(name: str, version: str) -> ChartMetadata | None:
    """Return the published chart's metadata, or None if it is not in OCI.

    Fail on errors other than not-found. Auth and network errors are not
    the same as a missing chart.
    """
    oci_ref = f"{CHART_OCI_PREFIX}/{name}"
    with tempfile.TemporaryDirectory(prefix="zep-dev-chart-") as destination:
        result = execute(
            "helm",
            "pull",
            oci_ref,
            "--version",
            version,
            "--destination",
            destination,
            capture_stdout=True,
            capture_stderr=True,
            check=False,
            timeout=_PULL_TIMEOUT,
        )
        if result.returncode == 0:
            package = Path(destination) / f"{name}-{version}.tgz"
            return _packaged_chart_metadata(package, name)

    detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
    message = detail.lower()
    if any(token in message for token in ("not found", "manifest unknown", "404")):
        return None
    raise RuntimeError(f"OCI error for {oci_ref}:{version}: {detail}.")


def _packaged_chart_metadata(package: Path, name: str) -> ChartMetadata:
    with tarfile.open(package, "r:gz") as archive:
        chart_yaml = archive.extractfile(f"{name}/Chart.yaml")
        if chart_yaml is None:
            raise RuntimeError(f"{package} has no {name}/Chart.yaml")
        return ChartMetadata.model_validate(yaml.safe_load(chart_yaml))
