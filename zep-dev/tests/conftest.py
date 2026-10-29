import os
from pathlib import Path
from types import ModuleType

import pytest

from tests.support.execution import FakeExecute, FakeExecuteFactory
from zep_dev import shared


@pytest.fixture(autouse=True)
def ambient_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No test probes a container engine, dumps a cluster, or writes ~/.cache."""
    monkeypatch.setenv("KIND_EXPERIMENTAL_PROVIDER", "podman")
    monkeypatch.delenv("CI_DUMP_DEBUG", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture
def cli_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Isolate CLI startup and restore variables it changes directly."""
    bin_dir = tmp_path / "cli-bin"
    bin_dir.mkdir()
    monkeypatch.setattr("zep_dev.cli.get_bin_dir", lambda: bin_dir)
    monkeypatch.setattr(shared, "get_bin_dir", lambda: bin_dir)
    # Register restoration before Click callbacks mutate os.environ.
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    monkeypatch.delenv("HELM_REGISTRY_CONFIG", raising=False)
    monkeypatch.setattr(shared, "REGISTRY_CONFIG_PATHS", ())


@pytest.fixture
def fake_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeExecuteFactory:
    def _install(module: ModuleType) -> FakeExecute:
        fake = FakeExecute()
        monkeypatch.setattr(module, "execute", fake)
        return fake

    return _install
