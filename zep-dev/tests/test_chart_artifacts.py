"""OCI wait timeout messaging."""

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from zep_dev import chart_artifacts
from zep_dev.chart_artifacts import ChartRef, wait_for_oci


@dataclass
class Clock:
    now: float = 100.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_wait_for_oci_times_out_with_actions_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = Clock()
    monkeypatch.setattr(
        chart_artifacts,
        "time",
        SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep),
    )
    monkeypatch.setattr(chart_artifacts, "_TIMEOUT", 100)
    monkeypatch.setattr(
        chart_artifacts, "probe_oci_chart", lambda *args, **kwargs: False
    )
    ref = ChartRef(
        name="ewb",
        version="1.2.3",
        source="commit",
        sha="a" * 40,
        repo_name="energy-workbench-server",
    )

    with pytest.raises(TimeoutError, match="Timed out waiting for ewb:1.2.3") as caught:
        wait_for_oci(ref)

    assert ref.sha is not None
    assert ref.sha in str(caught.value)
    assert "https://github.com/zepben/energy-workbench-server/actions" in str(
        caught.value
    )
