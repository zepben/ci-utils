"""CLI tests for checking pinned Distribution charts in OCI."""

from pathlib import Path
from subprocess import TimeoutExpired

import pytest
import yaml
from click.testing import CliRunner

from _fake_execute import FakeExecuteFactory
from zep_dev import cluster
from zep_dev.cli import cli
from zep_dev.oci import OCI_PROBE_TIMEOUT


def write_distribution(path: Path, components: dict[str, dict[str, object]]) -> str:
    content = yaml.safe_dump(
        {"metadata": {"name": "test-distribution"}, "components": components},
        sort_keys=False,
    )
    path.write_text(content, encoding="utf-8")
    return content


def test_build_checks_all_pins_in_component_order_without_mutation(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    path = tmp_path / "distribution.yaml"
    original = write_distribution(
        path,
        {
            "hcs": {"version": "2.0.0-6+2c6bb43"},
            "eas-web-client": {"version": "1.40.0"},
            "ewb": {"version": "0.0.0-3.13.0.7+e73c536"},
            "eas": {"version": "0.0.0-2.19.0.14+96274bc"},
        },
    )
    fake = fake_execute(cluster).on("helm", "show", "chart")

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code == 0, result.exception or result.output
    assert [call.args for call in fake.calls] == [
        (
            "helm",
            "show",
            "chart",
            f"oci://ghcr.io/zepben/charts/{name}",
            "--version",
            version,
        )
        for name, version in (
            ("ewb", "0.0.0-3.13.0.7+e73c536"),
            ("eas", "0.0.0-2.19.0.14+96274bc"),
            ("hcs", "2.0.0-6+2c6bb43"),
            ("eas-web-client", "1.40.0"),
        )
    ]
    assert all(
        call.kwargs
        == {
            "capture_stdout": True,
            "capture_stderr": True,
            "check": False,
            "timeout": OCI_PROBE_TIMEOUT,
        }
        for call in fake.calls
    )
    assert "OCI present eas-web-client:1.40.0" in result.output
    assert path.read_text(encoding="utf-8") == original


def test_build_stops_on_missing_chart_and_does_not_build(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    path = tmp_path / "distribution.yaml"
    original = write_distribution(
        path, {"ewb": {"version": "9.9.9"}, "eas": {"version": "1.0.0"}}
    )
    fake = fake_execute(cluster).on(
        "helm", "show", "chart", returncode=1, stderr="manifest unknown"
    )

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code != 0
    assert result.exception is not None
    message = str(result.exception)
    assert "OCI not-found for oci://ghcr.io/zepben/charts/ewb:9.9.9" in message
    assert "cannot build a version: locator" in message
    assert len(fake.calls) == 1
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize(
    ("stderr", "kind"),
    [
        ("401 Unauthorized", "auth"),
        ("403 Forbidden", "auth"),
        ("dial tcp: connection refused", "network"),
        ("unexpected Helm failure", "unknown"),
    ],
)
def test_build_reports_oci_failure_kind(
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    stderr: str,
    kind: str,
) -> None:
    path = tmp_path / "distribution.yaml"
    write_distribution(path, {"ewb": {"version": "1.0.0"}})
    fake_execute(cluster).on("helm", "show", "chart", returncode=1, stderr=stderr)

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code != 0
    assert result.exception is not None
    assert f"OCI {kind} for oci://ghcr.io/zepben/charts/ewb:1.0.0" in str(
        result.exception
    )


@pytest.mark.parametrize(
    ("content", "error"),
    [
        ("components: [\n", "while parsing"),
        (
            "metadata:\n  name: demo\ncomponents:\n  ewb:\n    version: ''\n",
            "components.ewb",
        ),
    ],
)
def test_build_reports_invalid_distribution_without_oci(
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    content: str,
    error: str,
) -> None:
    path = tmp_path / "distribution.yaml"
    path.write_text(content, encoding="utf-8")
    fake = fake_execute(cluster)

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code != 0
    assert result.exception is not None
    assert error in str(result.exception)
    assert fake.calls == []


def test_oci_probe_subprocess_timeout_is_reported(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    path = tmp_path / "distribution.yaml"
    write_distribution(path, {"ewb": {"version": "1.0.0"}})
    fake_execute(cluster).on(
        "helm", "show", "chart", raises=TimeoutExpired(["helm", "show", "chart"], 60)
    )

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code != 0
    assert result.exception is not None
    assert isinstance(result.exception, TimeoutExpired)
    assert result.exception.timeout == 60
