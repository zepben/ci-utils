from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from _fake_execute import FakeExecute, FakeExecuteFactory
from zep_dev import k8s_secrets, terraform_roots
from zep_dev.commands.terraform import commands as terraform_commands
from zep_dev.models import ChartTestingConfig
from zep_dev.profile import Profile

WriteProfile = Callable[..., Path]


@pytest.fixture(autouse=True)
def stub_tools_bin_dir(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI startup calls get_bin_dir().

    Avoid a need for an app virtualenv in tests.
    """
    bin_dir = tmp_path_factory.mktemp("zep-dev-bin")
    monkeypatch.setattr("zep_dev.cli.get_bin_dir", lambda: bin_dir)
    monkeypatch.setattr("zep_dev.shared.get_bin_dir", lambda: bin_dir)


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


@pytest.fixture
def write_distribution(tmp_path: Path) -> Callable[..., Path]:
    def write(filename: str = "dist.yaml", **charts: dict[str, object]) -> Path:
        path = tmp_path / filename
        path.write_text(
            yaml.safe_dump(
                {
                    "metadata": {"name": "platform-latest"},
                    "charts": charts or {"ewb": {"version": "1.0.0"}},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return path

    return write


@pytest.fixture
def write_profile(
    tmp_path: Path, write_distribution: Callable[..., Path]
) -> WriteProfile:
    def write(
        *,
        name: str = "demo",
        distribution: str = "dist.yaml",
        body: dict[str, Any] | None = None,
        **charts: dict[str, object],
    ) -> Path:
        write_distribution(distribution, **charts)
        profile: dict[str, Any] = {
            "metadata": {"name": name},
            "distribution": distribution,
            "namespace": "integration",
            "k8s": {
                "kind": {
                    "config": {
                        "kind": "Cluster",
                        "apiVersion": "kind.x-k8s.io/v1alpha4",
                        "nodes": [],
                    }
                }
            },
        }
        if body:
            if "k8s" in body:
                k8s = profile["k8s"]
                k8s.update(body["k8s"])
                body = {k: v for k, v in body.items() if k != "k8s"}
            profile.update(body)
        path = tmp_path / "profile.yaml"
        path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
        return path

    return write


@pytest.fixture
def generated_tf_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "generated"
    monkeypatch.setattr(terraform_roots, "GENERATED_TF_BASE", base)
    return base


@pytest.fixture
def state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "states"
    monkeypatch.setattr(terraform_commands, "STATE_ROOT", root)
    return root


@pytest.fixture
def contract_profile(write_profile: WriteProfile) -> Profile:
    return Profile.from_path(
        write_profile(
            body={
                "k8s": {
                    "components": [
                        {
                            "type": "cnpg",
                            "name": f"{app}-kind-pg",
                            "namespace": "integration",
                            "database": app,
                            "owner": app,
                            "password": "kind-password",
                            "spec": {"instances": 1},
                        }
                        for app in ("eas", "hcs")
                    ]
                },
                "runtime": {"databases": {"eas": "eas-kind-pg", "hcs": "hcs-kind-pg"}},
            }
        )
    )
