"""OCI wait timeout messaging."""

from pathlib import Path

import pytest

from tests.support.clock import FakeClock
from tests.support.execution import FakeExecuteFactory
from zep_dev.development_environments import chart_sources
from zep_dev.development_environments.chart_sources import (
    SourceChartRef,
    wait_for_oci,
)


def test_wait_for_oci_times_out_with_actions_context(
    monkeypatch: pytest.MonkeyPatch,
    fake_clock: FakeClock,
) -> None:
    monkeypatch.setattr(chart_sources, "_TIMEOUT", 100)
    monkeypatch.setattr(chart_sources, "published_chart_metadata", lambda *_args: None)
    ref = SourceChartRef(
        name="ewb",
        version="1.2.3",
        source="commit",
        sha="a" * 40,
        repo_name="energy-workbench-server",
        repo=Path("/unused/cache"),
    )

    with pytest.raises(TimeoutError, match="Timed out waiting for ewb:1.2.3") as caught:
        wait_for_oci(ref)

    assert ref.sha in str(caught.value)
    assert "https://github.com/zepben/energy-workbench-server/actions" in str(
        caught.value
    )


@pytest.mark.parametrize(
    "detail",
    ["401 Unauthorized", "connection refused"],
    ids=["authentication", "network"],
)
def test_oci_probe_propagates_errors_other_than_missing_chart(
    fake_execute: FakeExecuteFactory, detail: str
) -> None:
    fake_execute(chart_sources).on("helm", "pull", returncode=1, stderr=detail)
    with pytest.raises(RuntimeError, match=detail):
        chart_sources.probe_oci_chart("eas", "1.2.3", report=False)


@pytest.mark.parametrize("detail", ["manifest unknown", "404 Not Found"])
def test_oci_probe_identifies_missing_chart(
    fake_execute: FakeExecuteFactory, detail: str
) -> None:
    fake_execute(chart_sources).on("helm", "pull", returncode=1, stderr=detail)
    assert chart_sources.probe_oci_chart("eas", "1.2.3", report=False) is None
