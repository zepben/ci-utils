import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import call

import pytest

from _fake_execute import FakeExecute
from zep_dev import cluster, k8s
from zep_dev.shared import CommandResult


def test_kube_guard_keeps_kind_after_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kubeconfig = "/original/kubeconfig"
    provider_config = "/original/provider-config"
    monkeypatch.setenv("KUBECONFIG", kubeconfig)
    monkeypatch.setenv("KUBE_CONFIG_PATH", provider_config)

    with pytest.raises(RuntimeError, match="terraform failure"):
        with k8s.kube_guard():
            assert os.environ["KUBECONFIG"] == str(k8s.KUBECONF_PATH)
            assert os.environ["KUBE_CONFIG_PATH"] == str(k8s.KUBECONF_PATH)
            raise RuntimeError("terraform failure")

    assert os.environ["KUBECONFIG"] == str(k8s.KUBECONF_PATH)
    assert os.environ["KUBE_CONFIG_PATH"] == str(k8s.KUBECONF_PATH)


def test_parallel_helm_calls_keep_kind_after_first_call_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KUBECONFIG", "/original/kubeconfig")
    monkeypatch.setenv("KUBE_CONFIG_PATH", "/original/provider-config")
    second_started = Event()
    first_finished = Event()
    observed: list[tuple[str, str]] = []

    def fake_execute(*args: str, **_kwargs: object) -> CommandResult:
        if args[1] == "first":
            assert second_started.wait(timeout=3)
        else:
            second_started.set()
            assert first_finished.wait(timeout=3)
            observed.append((os.environ["KUBECONFIG"], os.environ["KUBE_CONFIG_PATH"]))
        return CommandResult(0, "", "")

    monkeypatch.setattr(cluster, "execute", fake_execute)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(cluster.helm, "first")
        second = pool.submit(cluster.helm, "second")
        try:
            first.result(timeout=3)
        finally:
            first_finished.set()
        second.result(timeout=3)

    assert observed == [(str(k8s.KUBECONF_PATH), str(k8s.KUBECONF_PATH))]


@pytest.mark.parametrize(
    ("resource", "name", "namespace", "stdout", "expected", "expected_call"),
    [
        (
            "secret",
            "credentials",
            "test-ns",
            "secret/credentials\n",
            True,
            call(
                "get",
                "secret",
                "credentials",
                "--ignore-not-found",
                "--output=name",
                "--namespace=test-ns",
                capture_stdout=True,
            ),
        ),
        (
            "secret",
            "credentials",
            "test-ns",
            "",
            False,
            call(
                "get",
                "secret",
                "credentials",
                "--ignore-not-found",
                "--output=name",
                "--namespace=test-ns",
                capture_stdout=True,
            ),
        ),
        (
            "namespace",
            "test-ns",
            None,
            "namespace/test-ns\n",
            True,
            call(
                "get",
                "namespace",
                "test-ns",
                "--ignore-not-found",
                "--output=name",
                capture_stdout=True,
            ),
        ),
    ],
)
def test_resource_exists(
    monkeypatch: pytest.MonkeyPatch,
    resource: str,
    name: str,
    namespace: str | None,
    stdout: str,
    expected: bool,
    expected_call: object,
) -> None:
    fake = FakeExecute().on("get", resource, name, stdout=stdout)
    monkeypatch.setattr(k8s, "kubectl", fake)

    assert k8s.resource_exists(resource, name, namespace=namespace) is expected
    assert fake.calls == [expected_call]


def test_resource_exists_propagates_kubectl_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeExecute().on(
        "get",
        "secret",
        "credentials",
        stderr="Forbidden",
        returncode=1,
    )
    monkeypatch.setattr(k8s, "kubectl", fake)

    with pytest.raises(subprocess.CalledProcessError):
        k8s.resource_exists("secret", "credentials", namespace="test-ns")
