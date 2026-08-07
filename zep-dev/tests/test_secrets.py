from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

import pytest
from click.testing import CliRunner

from _fake_execute import FakeExecute
from zep_dev import k8s_secrets
from zep_dev.cli import cli
from zep_dev.k8s_secrets import IMAGE_SECRET_NAME


@pytest.fixture
def fake_kubectl(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[ModuleType], FakeExecute]:
    def _install(module: ModuleType) -> FakeExecute:
        fake = FakeExecute()
        monkeypatch.setattr(module, "kubectl", fake)
        return fake

    return _install


def test_secrets_create_when_absent(
    auth_json: Path,
    fake_kubectl: Callable[[ModuleType], FakeExecute],
) -> None:
    fake = (
        fake_kubectl(k8s_secrets).on("get", "secrets", stdout="").on("create", "secret")
    )

    result = CliRunner().invoke(cli, ["secrets", "create", "--namespace", "test-ns"])

    assert result.exit_code == 0, result.output
    assert fake.calls_for("create", "secret") == [
        call(
            "create",
            "secret",
            "generic",
            IMAGE_SECRET_NAME,
            "--namespace=test-ns",
            f"--from-file=.dockerconfigjson={auth_json}",
            "--type=kubernetes.io/dockerconfigjson",
        )
    ]


def test_secrets_create_skips_when_present(
    auth_json: Path,
    fake_kubectl: Callable[[ModuleType], FakeExecute],
) -> None:
    fake = fake_kubectl(k8s_secrets).on(
        "get",
        "secrets",
        stdout=f"{IMAGE_SECRET_NAME}   Opaque   1   1s\n",
    )

    result = CliRunner().invoke(cli, ["secrets", "create", "--namespace", "test-ns"])

    assert result.exit_code == 0, result.output
    assert fake.calls_for("create", "secret") == []


def test_secrets_create_fails_without_auth(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_kubectl: FakeExecute,
) -> None:
    missing = tmp_path / "missing-auth.json"
    monkeypatch.setattr(k8s_secrets, "IMAGE_SECRET_PATHS", [missing])

    result = CliRunner().invoke(cli, ["secrets", "create", "--namespace", "test-ns"])

    assert result.exit_code != 0
    assert "Failed to locate auth.json" in result.output
