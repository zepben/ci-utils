import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from tests.support.execution import FakeExecuteFactory, option_value
from zep_dev.development_environments import helm
from zep_dev.development_environments.chart_sources import VersionChartRef
from zep_dev.development_environments.services import HelmService
from zep_dev.development_environments.target import execution_target


def test_parallel_application_processes_receive_their_own_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(helm, "resolve", lambda _name: None)
    monkeypatch.setenv("KUBECONFIG", "/hostile/default")
    launched: list[tuple[list[str], dict[str, str]]] = []

    class FinishedProcess:
        returncode = 0

        def __init__(self, args: list[str]) -> None:
            self.args = args

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            return "", ""

    def launch(args: list[str], **kwargs: Any) -> FinishedProcess:
        launched.append((args, kwargs["env"]))
        return FinishedProcess(args)

    monkeypatch.setattr(subprocess, "Popen", launch)
    refs = [
        VersionChartRef(name="eas", version="1.0", source="version"),
        VersionChartRef(name="hcs", version="1.0", source="version"),
    ]
    for name in ("first", "second"):
        target = execution_target(name, environ={"XDG_STATE_HOME": str(tmp_path)})
        helm.install_applications(target, refs, {})
    assert len(launched) == 4
    for name in ("first", "second"):
        calls = [
            (args, env)
            for args, env in launched
            if option_value(args, "--kube-context") == f"kind-zep-dev-{name}"
        ]
        assert len(calls) == len(refs)
        target = execution_target(name, environ={"XDG_STATE_HOME": str(tmp_path)})
        for args, env in calls:
            assert option_value(args, "--kubeconfig") == str(target.kubeconfig)
            assert option_value(args, "--kube-context") == target.context
            assert env["KUBECONFIG"] == str(target.kubeconfig)
    assert os.environ["KUBECONFIG"] == "/hostile/default"


def test_failed_application_install_stops_sibling_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = execution_target("failed", environ={"XDG_STATE_HOME": str(tmp_path)})
    monkeypatch.setattr(helm, "resolve", lambda _name: None)
    stopped: list[int] = []

    class Process:
        def __init__(self, args: list[str], pid: int, returncode: int) -> None:
            self.args = args
            self.pid = pid
            self.returncode = returncode

        def communicate(self, timeout: float | None = None) -> tuple[str, str]:
            if self.returncode == 0 and not stopped:
                raise subprocess.TimeoutExpired(self.args, timeout or 0.1)
            return "", "failure" if self.returncode else ""

    processes = [Process(["helm", "eas"], 101, 1), Process(["helm", "hcs"], 102, 0)]
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: processes.pop(0))
    monkeypatch.setattr(os, "killpg", lambda pid, _signal: stopped.append(pid))
    refs = [
        VersionChartRef(name="eas", version="1.0", source="version"),
        VersionChartRef(name="hcs", version="1.0", source="version"),
    ]
    with pytest.raises(subprocess.CalledProcessError):
        helm.install_applications(target, refs, {})
    assert 102 in stopped


def test_helm_service_values_layers_and_target(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    service = HelmService.model_validate(
        {
            "type": "helm",
            "chart": "argo-cd",
            "repository": "https://example.org/charts",
            "version": "1",
            "values": {"configs": {"cm": {"a": "base"}}},
        }
    )
    overlay = {"configs": {"cm": {"a": "overlay"}}}
    layers: list[dict[str, Any]] = []

    def inspect(args: tuple[str, ...], _kwargs: dict[str, object]) -> None:
        for index, argument in enumerate(args):
            if argument == "-f":
                layers.append(yaml.safe_load(Path(args[index + 1]).read_text()))

    calls = fake_execute(helm).on("helm", "install", hook=inspect)
    helm.install_service(target, "argo", service, overlay)
    assert layers == [service.values, overlay]
    [install] = calls.calls
    assert option_value(install.args, "--kubeconfig") == str(target.kubeconfig)
    assert option_value(install.args, "--kube-context") == target.context


@pytest.mark.parametrize(
    "response",
    [
        "{}",
        "[null]",
        '[{"namespace": 123, "name": "app", "status": "deployed"}]',
        '[{"namespace": "default", "name": false, "status": "deployed"}]',
        '[{"namespace": "default", "status": "deployed"}]',
        '[{"namespace": "default", "name": "app"}]',
    ],
    ids=[
        "not-a-list",
        "not-a-release",
        "invalid-namespace",
        "invalid-name",
        "missing-name",
        "missing-status",
    ],
)
def test_release_statuses_rejects_invalid_response(
    tmp_path: Path, fake_execute: FakeExecuteFactory, response: str
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    fake_execute(helm).on("helm", "list", stdout=response)
    with pytest.raises(ValidationError):
        helm.release_statuses(target)
