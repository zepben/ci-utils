"""Read charts published to the zepben OCI chart repository."""

import yaml

from zep_dev.errors import ZepDevError
from zep_dev.models import ChartMetadata
from zep_dev.shared import execute

CHART_REPOSITORY = "ghcr.io/zepben/charts"
CHART_OCI_PREFIX = f"oci://{CHART_REPOSITORY}"
_TIMEOUT = 60


def published_chart_metadata(name: str, version: str) -> ChartMetadata | None:
    """Return the published chart's metadata, or None if it is not in OCI.

    Only Helm's not-found phrasings mean missing. Auth and network errors are
    not the same as a missing chart.
    """
    oci_ref = f"{CHART_OCI_PREFIX}/{name}"
    result = execute(
        "helm",
        "show",
        "chart",
        oci_ref,
        "--version",
        version,
        capture_stdout=True,
        capture_stderr=True,
        check=False,
        timeout=_TIMEOUT,
    )
    if result.returncode == 0:
        return ChartMetadata.model_validate(yaml.safe_load(result.stdout))
    detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
    if any(phrase in detail.lower() for phrase in ("not found", "manifest unknown")):
        return None
    raise ZepDevError(f"OCI error for {oci_ref}:{version}: {detail}")
