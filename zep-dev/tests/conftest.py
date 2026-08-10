from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from _fake_execute import FakeExecute
from zep_dev import k8s_secrets


@pytest.fixture
def fake_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[ModuleType], FakeExecute]:
    def _install(module: ModuleType) -> FakeExecute:
        fake = FakeExecute()
        monkeypatch.setattr(module, "execute", fake)
        return fake

    return _install


@pytest.fixture
def auth_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "auth.json"
    path.write_text("{}\n")
    monkeypatch.setattr(k8s_secrets, "IMAGE_SECRET_PATHS", [path])
    return path


@pytest.fixture
def helm_dir(tmp_path: Path) -> Path:
    d = tmp_path / "helm"
    d.mkdir()
    (d / "ct.yaml").write_text("namespace: test-ns\n")
    return d
