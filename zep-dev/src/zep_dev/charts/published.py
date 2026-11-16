"""Read charts published to the zepben OCI chart repository."""

from pathlib import Path
from tempfile import TemporaryDirectory

from zep_dev.errors import ZepDevError
from zep_dev.models import ChartMetadata
from zep_dev.shared import execute

CHART_REPOSITORY = "ghcr.io/zepben/charts"
CHART_OCI_PREFIX = f"oci://{CHART_REPOSITORY}"
_TIMEOUT = 60


def is_missing_chart(output: str) -> bool:
    """Whether Helm's output says the chart or version is absent.

    Auth and network failures are not missing charts.
    """
    text = output.lower()
    return "not found" in text or "manifest unknown" in text


def published_chart_metadata(name: str, version: str) -> ChartMetadata | None:
    """Return the published chart's metadata, or None if it is not in OCI.

    The chart is pulled and its Chart.yaml read from disk. Stdout is never parsed.
    """
    oci_ref = f"{CHART_OCI_PREFIX}/{name}"
    with TemporaryDirectory(prefix="zep-dev-published-") as directory:
        result = execute(
            "helm",
            "pull",
            oci_ref,
            "--version",
            version,
            "--untar",
            "--destination",
            directory,
            # Helm's pull notices go to stdout; capture them so they do not
            # reach the caller's stdout, which some commands keep machine-readable.
            capture_stdout=True,
            capture_stderr=True,
            check=False,
            timeout=_TIMEOUT,
        )
        if result.returncode == 0:
            return ChartMetadata.from_chart_dir(Path(directory) / name)
    detail = result.stderr.strip() or f"exit {result.returncode}"
    if is_missing_chart(detail):
        return None
    raise ZepDevError(f"OCI error for {oci_ref}:{version}: {detail}")
