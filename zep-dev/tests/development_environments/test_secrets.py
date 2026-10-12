from pathlib import Path

import pytest

from tests.support.execution import FakeExecuteFactory, call
from zep_dev.development_environments import kubernetes, secrets
from zep_dev.development_environments.bindings import SecretSource
from zep_dev.development_environments.target import (
    execution_target,
    kubernetes_environment,
)


@pytest.mark.parametrize(
    "exists", [False, True], ids=["create-missing", "preserve-existing"]
)
@pytest.mark.parametrize("source_kind", ["env", "file"])
def test_bound_secret_preserves_existing_value_or_uses_current_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
    exists: bool,
    source_kind: str,
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    if source_kind == "env":
        monkeypatch.setenv("APP_CREDENTIALS", "TOKEN=current")
        source = SecretSource(env="APP_CREDENTIALS")
    else:
        path = tmp_path / "credentials.env"
        path.write_text("TOKEN=current")
        source = SecretSource(file=path)
    prefix = (
        "kubectl",
        f"--kubeconfig={target.kubeconfig}",
        f"--context={target.context}",
    )
    calls = (
        fake_execute(kubernetes)
        .on(*prefix, "get", stdout="secret/credentials" if exists else "")
        .on(*prefix, "--namespace=integration", "create", "secret")
    )
    secrets.create_bound_secret(target, "credentials", source)
    created = calls.calls_for(*prefix, "--namespace=integration", "create")
    if exists:
        assert created == []
    else:
        assert created == [
            call(
                *prefix,
                "--namespace=integration",
                "create",
                "secret",
                "generic",
                "credentials",
                "--from-env-file=/dev/stdin",
                capture_stdout=False,
                capture_stderr=True,
                check=False,
                input="TOKEN=current",
                env=kubernetes_environment(target),
            )
        ]


@pytest.mark.parametrize(
    "exists", [False, True], ids=["create-missing", "preserve-existing"]
)
def test_image_pull_secret_is_created_only_when_missing(
    tmp_path: Path, registry_auth: Path, fake_execute: FakeExecuteFactory, exists: bool
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    prefix = (
        "kubectl",
        f"--kubeconfig={target.kubeconfig}",
        f"--context={target.context}",
    )
    calls = (
        fake_execute(kubernetes)
        .on(*prefix, "get", stdout="secret/github-registry" if exists else "")
        .on(*prefix, "create", "secret")
    )
    secrets.create_image_pull_secret(target, target.namespace)
    created = calls.calls_for(*prefix, "create", "secret")
    if exists:
        assert created == []
    else:
        [creation] = created
        assert f"--from-file=.dockerconfigjson={registry_auth}" in creation.args
        assert "--type=kubernetes.io/dockerconfigjson" in creation.args


@pytest.mark.parametrize("missing_value", [None, ""], ids=["missing", "empty"])
def test_standalone_secret_file_resolves_values_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, missing_value: str | None
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    source = tmp_path / "ci-secrets.yaml"
    source.write_text(
        "secrets:\n"
        "  - name: first\n"
        "    env_var: FIRST_SECRET\n"
        "  - name: second\n"
        "    env_var: SECOND_SECRET\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("FIRST_SECRET", "KEY=value")
    if missing_value is None:
        monkeypatch.delenv("SECOND_SECRET", raising=False)
    else:
        monkeypatch.setenv("SECOND_SECRET", missing_value)
    created: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        secrets,
        "create_env_file_secret",
        lambda _target, namespace, name, content: created.append(
            (namespace, name, content)
        ),
    )
    with pytest.raises(ValueError, match="SECOND_SECRET is not set"):
        secrets.create_additional_secrets(target, "test", source)
    assert created == []
    monkeypatch.setenv("SECOND_SECRET", "TOKEN=secret")
    secrets.create_additional_secrets(target, "test", source)
    assert created == [
        ("test", "first", "KEY=value"),
        ("test", "second", "TOKEN=secret"),
    ]


@pytest.mark.parametrize(
    "auth", [123, {"token": "private-value"}], ids=["number", "mapping"]
)
def test_invalid_registry_credentials_are_rejected_without_exposing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, auth: object
) -> None:
    import json

    path = tmp_path / "auth.json"
    path.write_text(json.dumps({"auths": {"ghcr.io": {"auth": auth}}}))
    monkeypatch.setattr(secrets, "IMAGE_SECRET_PATHS", (path,))
    with pytest.raises(
        ValueError, match="invalid container registry configuration"
    ) as failure:
        secrets.resolve_registry_credential("ghcr.io")
    assert "private-value" not in str(failure.value)
    assert failure.value.__suppress_context__


def test_image_pull_secret_uses_the_registry_selected_by_preflight(
    tmp_path: Path,
    registry_auth: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    unrelated_auth = tmp_path / "unrelated-auth.json"
    unrelated_auth.write_text('{"auths": {}}', encoding="utf-8")
    monkeypatch.setattr(secrets, "IMAGE_SECRET_PATHS", (unrelated_auth, registry_auth))
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    prefix = (
        "kubectl",
        f"--kubeconfig={target.kubeconfig}",
        f"--context={target.context}",
    )
    calls = fake_execute(kubernetes).on(*prefix, "get").on(*prefix, "create", "secret")

    assert secrets.resolve_registry_credential("ghcr.io") == (
        "test-user",
        "test-password",
    )
    secrets.create_image_pull_secret(target, target.namespace)

    [creation] = calls.calls_for(*prefix, "create", "secret")
    assert f"--from-file=.dockerconfigjson={registry_auth}" in creation.args
