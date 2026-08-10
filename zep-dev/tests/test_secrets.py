import base64
import json
from pathlib import Path
from unittest.mock import call

import pytest
from click import ClickException
from click.testing import CliRunner

from _fake_execute import FakeExecute
from zep_dev import k8s, k8s_secrets
from zep_dev.cli import cli
from zep_dev.k8s_secrets import IMAGE_SECRET_NAME


def test_resolve_registry_credential_selects_registry_and_has_secret_free_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    auth_path = tmp_path / "auth.json"
    requested_auth = base64.b64encode(b"octocat:ghp_requested").decode()
    other_auth = base64.b64encode(b"other:ghp_other").decode()
    auth_path.write_text(
        json.dumps(
            {
                "auths": {
                    "example.com": {"auth": other_auth},
                    "ghcr.io": {"auth": requested_auth},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(k8s_secrets, "IMAGE_SECRET_PATHS", [auth_path])

    assert k8s_secrets.resolve_registry_credential("ghcr.io") == (
        "octocat",
        "ghp_requested",
    )

    with pytest.raises(ClickException) as exc_info:
        k8s_secrets.resolve_registry_credential("missing.example.com")
    error = str(exc_info.value)
    assert "missing.example.com" in error
    assert requested_auth not in error
    assert "ghp_requested" not in error
    assert other_auth not in error
    assert "ghp_other" not in error


@pytest.fixture
def fake_kubectl(
    monkeypatch: pytest.MonkeyPatch,
) -> FakeExecute:
    fake = FakeExecute().on(
        "get",
        "namespace",
        "test-ns",
        stdout="namespace/test-ns\n",
    )
    monkeypatch.setattr(k8s, "kubectl", fake)
    monkeypatch.setattr(k8s_secrets, "kubectl", fake)
    return fake


def test_secrets_create_when_absent(
    auth_json: Path,
    fake_kubectl: FakeExecute,
) -> None:
    fake = fake_kubectl.on("get", "secret", IMAGE_SECRET_NAME, stdout="").on(
        "create", "secret"
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
    fake_kubectl: FakeExecute,
) -> None:
    fake = fake_kubectl.on(
        "get",
        "secret",
        IMAGE_SECRET_NAME,
        stdout=f"secret/{IMAGE_SECRET_NAME}\n",
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
