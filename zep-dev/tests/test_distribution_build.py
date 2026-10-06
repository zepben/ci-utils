"""Build checks Distribution pins in OCI. It does not change the file."""

from collections.abc import Callable
from pathlib import Path

from click.testing import CliRunner

from _fake_execute import FakeExecuteFactory
from zep_dev import cluster
from zep_dev.cli import cli


def test_build_checks_all_pins_in_component_order_without_mutation(
    write_distribution: Callable[..., Path], fake_execute: FakeExecuteFactory
) -> None:
    path = write_distribution(
        hcs={"version": "2.0.0"},
        ewb={"version": "1.0.0"},
        eas={"version": "1.1.0"},
    )
    original = path.read_text(encoding="utf-8")
    fake = fake_execute(cluster).on("helm", "show", "chart")

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code == 0, result.exception or result.output
    assert [
        arg for call in fake.calls for arg in call.args if arg.startswith("oci://")
    ] == [
        "oci://ghcr.io/zepben/charts/ewb",
        "oci://ghcr.io/zepben/charts/eas",
        "oci://ghcr.io/zepben/charts/hcs",
    ]
    assert path.read_text(encoding="utf-8") == original


def test_build_stops_on_missing_chart_and_does_not_build(
    write_distribution: Callable[..., Path], fake_execute: FakeExecuteFactory
) -> None:
    path = write_distribution(ewb={"version": "9.9.9"}, eas={"version": "1.0.0"})
    fake = fake_execute(cluster).on(
        "helm", "show", "chart", returncode=1, stderr="manifest unknown"
    )

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code != 0
    assert result.exception is not None
    assert "OCI not-found" in str(result.exception)
    assert "cannot build a version: locator" in str(result.exception)
    assert len(fake.calls) == 1
