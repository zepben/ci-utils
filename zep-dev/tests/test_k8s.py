import os
import subprocess
from unittest.mock import call

import pytest

from _fake_execute import FakeExecute
from zep_dev import k8s


def test_kube_guard_targets_kind_and_restores_after_failure(
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

    assert os.environ["KUBECONFIG"] == kubeconfig
    assert os.environ["KUBE_CONFIG_PATH"] == provider_config


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
