from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from _fake_execute import FakeExecute, FakeExecuteFactory
from zep_dev import k8s_secrets
from zep_dev.models import ChartTestingConfig


@pytest.fixture
def fake_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeExecuteFactory:
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


@pytest.fixture
def chart_testing_config() -> ChartTestingConfig:
    return ChartTestingConfig.model_validate(
        {
            "remote": "origin",
            "target-branch": "main",
            "chart-dirs": ["charts"],
            "chart-repos": ["example-repo=https://example.com/helm-charts"],
            "validate-maintainers": False,
            "check-version-increment": False,
            "namespace": "chart-testing",
            "release-label": "app.kubernetes.io/instance",
            "additional-commands": [],
        }
    )


@pytest.fixture
def write_chart_testing_config(
    helm_dir: Path,
) -> Callable[[ChartTestingConfig], None]:
    def write(config: ChartTestingConfig) -> None:
        (helm_dir / "ct.yaml").write_text(
            yaml.safe_dump(
                config.model_dump(by_alias=True, mode="json"), sort_keys=False
            )
        )

    return write
