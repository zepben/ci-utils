"""Check published application charts in GHCR with Helm."""

import json
import os
from pathlib import Path
from typing import Literal

from click import echo

from zep_dev import cluster
from zep_dev.distribution import CHART_OCI_PREFIX, ComponentName
from zep_dev.shared import resolve_registry_config

OciFailureKind = Literal["auth", "not-found", "network", "unknown"]
OCI_PROBE_TIMEOUT = 60


def _classify_oci_failure(stderr: str) -> OciFailureKind:
    message = stderr.lower()
    if any(
        token in message
        for token in (
            "unauthorized",
            "authentication",
            "denied",
            "forbidden",
            "401",
            "403",
        )
    ):
        return "auth"
    if any(
        token in message
        for token in (
            "timeout",
            "timed out",
            "connection refused",
            "connection reset",
            "temporary failure",
            "no such host",
            "dial tcp",
            "i/o timeout",
        )
    ):
        return "network"
    if any(token in message for token in ("not found", "manifest unknown", "404")):
        return "not-found"
    if "network" in message:
        return "network"
    return "unknown"


def probe_oci_chart(
    name: ComponentName,
    version: str,
    *,
    report: bool = True,
    timeout: float = OCI_PROBE_TIMEOUT,
) -> bool:
    """Return whether a chart exists; fail on errors other than not-found."""
    oci_ref = f"{CHART_OCI_PREFIX}/{name}"
    if report:
        echo(f"  checking OCI {name}:{version}")
    result = cluster.helm(
        "show",
        "chart",
        oci_ref,
        "--version",
        version,
        capture_stdout=True,
        capture_stderr=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode == 0:
        if report:
            echo(f"  OCI present {name}:{version}")
        return True

    kind = _classify_oci_failure(result.stderr or result.stdout)
    if kind == "not-found":
        return False
    detail = (result.stderr or result.stdout).strip() or f"exit {result.returncode}"
    raise RuntimeError(f"OCI {kind} for {oci_ref}:{version}: {detail}.")


def check_oci_chart(name: ComponentName, version: str) -> None:
    """Require the exact published chart version; never trigger a build."""
    if not probe_oci_chart(name, version):
        raise FileNotFoundError(
            f"OCI not-found for {CHART_OCI_PREFIX}/{name}:{version}. "
            "Publish this version or change the Distribution pin; "
            "distribution build cannot build a version: locator."
        )


def require_ghcr_credentials() -> None:
    """Check that Helm has a configured GHCR credential before dispatch."""
    configured = os.environ.get("HELM_REGISTRY_CONFIG")
    path = Path(configured) if configured else resolve_registry_config()
    if path is None:
        raise FileNotFoundError(
            "GHCR credentials missing; run helm registry login ghcr.io"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        auths = data.get("auths", {})
        available = (
            "ghcr.io" in auths
            or "ghcr.io" in data.get("credHelpers", {})
            or bool(data.get("credsStore"))
        )
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise ValueError(f"Invalid Helm registry config at {path}") from exc
    if not available:
        raise FileNotFoundError(
            "GHCR credentials missing; run helm registry login ghcr.io"
        )
