import base64
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any, Unpack

import pytest
import yaml

from tests.support.clock import FakeClock
from tests.support.execution import FakeExecute, FakeExecuteFactory
from tests.support.fixtures import (
    BindingsPayload,
    DistributionPayload,
    PrepareKind,
    WriteBindings,
    WriteDistribution,
)
from tests.support.resolvers import RecordingChartResolver
from zep_dev.development_environments import (
    chart_sources,
    kind,
    kubernetes,
    lifecycle,
    secrets,
)


@pytest.fixture(autouse=True)
def container_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KIND_EXPERIMENTAL_PROVIDER", "podman")


@pytest.fixture
def write_template(tmp_path: Path) -> Callable[[dict[str, Any]], Path]:
    def write(body: dict[str, Any]) -> Path:
        path = tmp_path / "template.yaml"
        path.write_text(yaml.safe_dump(body, sort_keys=False), encoding="utf-8")
        return path

    return write


@pytest.fixture
def basic_template() -> dict[str, Any]:
    return {
        "metadata": {"name": "integration"},
        "cluster": {
            "kind": {
                "kind": "Cluster",
                "apiVersion": "kind.x-k8s.io/v1alpha4",
                "nodes": [{"role": "control-plane"}, {"role": "worker"}],
            }
        },
    }


@pytest.fixture
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep operational files and Bindings discovery inside the test directory."""
    root = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("ZEP_DEV_BINDINGS", raising=False)
    monkeypatch.chdir(tmp_path)
    return root


@pytest.fixture
def prepare_kind(fake_execute: FakeExecuteFactory, state_home: Path) -> PrepareKind:
    def install(*, present: bool = False, name: str = "integration") -> FakeExecute:
        def write_kubeconfig(args: tuple[str, ...], _kwargs: dict[str, object]) -> None:
            path = Path(args[args.index("--kubeconfig") + 1])
            path.write_text("targeted kubeconfig", encoding="utf-8")

        return (
            fake_execute(kind)
            .on(
                "kind",
                "get",
                "clusters",
                "--quiet",
                stdout=f"zep-dev-{name}\n" if present else "",
            )
            .on("kind", "create", "cluster", hook=write_kubeconfig)
            .on("kind", "export", "kubeconfig", hook=write_kubeconfig)
        )

    return install


@pytest.fixture
def prepare_kubectl(fake_execute: FakeExecuteFactory) -> Callable[[], FakeExecute]:
    return lambda: fake_execute(kubernetes).on("kubectl")


@pytest.fixture
def write_bindings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WriteBindings:
    def write(**groups: Unpack[BindingsPayload]) -> Path:
        path = tmp_path / "bindings.yaml"
        path.write_text(yaml.safe_dump(groups, sort_keys=False), encoding="utf-8")
        monkeypatch.setenv("ZEP_DEV_BINDINGS", str(path))
        return path

    return write


@pytest.fixture
def deployments_checkout(tmp_path: Path) -> Path:
    """Local input shape only; wrapper compatibility belongs to its owning repository."""
    checkout = tmp_path / "deployments"
    subprocess.run(["git", "init", "-q", str(checkout)], check=True)
    for name in ("eas", "hcs"):
        (checkout / f"terraform/modules/kubernetes/{name}-kind-runtime-contract").mkdir(
            parents=True
        )
    return checkout


@pytest.fixture
def write_distribution(tmp_path: Path) -> WriteDistribution:
    def write(
        filename: str = "dist.yaml", **charts: Unpack[DistributionPayload]
    ) -> Path:
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
def chart_resolver(monkeypatch: pytest.MonkeyPatch) -> RecordingChartResolver:
    resolver = RecordingChartResolver()
    monkeypatch.setattr(lifecycle, "ChartResolver", lambda: resolver)
    return resolver


@pytest.fixture
def registry_auth(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "auth.json"
    credential = base64.b64encode(b"test-user:test-password").decode()
    path.write_text(
        json.dumps({"auths": {"ghcr.io": {"auth": credential}}}), encoding="utf-8"
    )
    monkeypatch.setattr(secrets, "IMAGE_SECRET_PATHS", (path,))
    return path


@pytest.fixture
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr(chart_sources, "time", clock)
    return clock
