"""Composed checks for provisioning order and generated inputs."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import create_autospec

import pytest
import yaml

from tests.support.execution import FakeExecute, FakeExecuteFactory
from tests.support.fixtures import PrepareKind, WriteBindings, WriteDistribution
from zep_dev.development_environments import (
    argo,
    cnpg,
    helm,
    kind,
    kubernetes,
    lifecycle,
    secrets,
    supporting,
)
from zep_dev.development_environments.target import execution_target


def test_missing_manifest_fails_before_kind(
    write_distribution: WriteDistribution,
    state_home: Path,
    prepare_kind: PrepareKind,
    tmp_path: Path,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> None:
    write_distribution(eas={"version": "1.0.0"})
    manifest = tmp_path / "resources.yaml"
    basic_template.update(
        {
            "distribution": "dist.yaml",
            "applications": {"eas": {"manifests": [manifest.name]}},
        }
    )
    calls = prepare_kind()
    with pytest.raises(FileNotFoundError):
        lifecycle.create_environment(write_template(basic_template))
    assert calls.calls == []
    assert not execution_target("integration").directory.exists()


@pytest.mark.parametrize(
    "installed_namespace",
    ["elsewhere", "operators"],
    ids=["different-namespace", "already-installed"],
)
def test_release_identity_controls_install_but_always_waits(
    state_home: Path,
    prepare_kind: PrepareKind,
    prepare_kubectl: Callable[[], FakeExecute],
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    fake_execute: FakeExecuteFactory,
    installed_namespace: str,
) -> None:
    basic_template["services"] = {
        "operator": {
            "type": "helm",
            "chart": "operator",
            "repository": "https://example.org/charts",
            "version": "1",
            "namespace": "operators",
            "wait_for": [
                {
                    "resource": "deployment/operator",
                    "for": "condition=Available",
                    "timeout": "60s",
                }
            ],
        }
    }
    prepare_kind(present=True)
    kubectl_calls = prepare_kubectl()
    helm_calls = (
        fake_execute(helm)
        .on(
            "helm",
            "list",
            stdout=json.dumps(
                [
                    {
                        "name": "operator",
                        "namespace": installed_namespace,
                        "status": "deployed",
                    }
                ]
            ),
        )
        .on("helm", "install")
    )
    template = write_template(basic_template)

    lifecycle.create_environment(template, allow_reuse=True)

    assert bool(helm_calls.calls_for("helm", "install")) is (
        installed_namespace != "operators"
    )
    [wait] = [command for command in kubectl_calls.calls if "wait" in command.args]
    assert "deployment/operator" in wait.args


def test_argo_mounts_and_overlay_come_from_consumed_binding(
    deployments_checkout: Path,
    write_bindings: WriteBindings,
    state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    fake_execute: FakeExecuteFactory,
) -> None:
    checkout = deployments_checkout
    write_bindings(repositories={"deployments": str(checkout)})
    basic_template["inputs"] = {"repositories": ["deployments", "unused"]}
    basic_template["services"] = {
        "argo": {
            "type": "helm",
            "chart": "argo-cd",
            "repository": "https://example.org/charts",
            "version": "1",
            "integration": {"type": "argo-cd", "repositories": ["deployments"]},
        }
    }
    plan = lifecycle.preflight(write_template(basic_template))
    assert plan.inputs.argo_repositories == {"deployments": checkout}
    assert plan.mounts == (
        kind.HostMount(checkout, "/mnt/local-repos/deployments", True),
    )
    overlay = argo.repository_overlay([checkout])
    assert (
        overlay["configs"]["repositories"]["local-deployments"]["url"]
        == "file:///mnt/local-repos/deployments"
    )
    [repository_mount] = overlay["repoServer"]["volumeMounts"]
    assert repository_mount["mountPath"] == "/mnt/local-repos"
    calls = fake_execute(kind).on(
        "kind", "get", "clusters", "--quiet", stdout="zep-dev-integration\n"
    )
    validate_mounts = create_autospec(kind.validate_existing_worker_mounts)
    monkeypatch.setattr(kind, "validate_existing_worker_mounts", validate_mounts)
    monkeypatch.setattr(kind, "export_kubeconfig", lambda _target: None)
    monkeypatch.setattr(kubernetes, "ensure_namespace", lambda *_args: None)
    monkeypatch.setattr(
        kubernetes, "apply_builtin_storage_classes", lambda *_args: None
    )
    monkeypatch.setattr(
        helm,
        "release_statuses",
        lambda _target: {("integration", "argo"): "deployed"},
    )
    monkeypatch.setattr(helm, "install_service", lambda *_args: None)
    lifecycle.create_environment(write_template(basic_template), allow_reuse=True)
    assert len(calls.calls_for("kind", "get")) == 1
    validate_mounts.assert_called_once_with(plan.target, plan.mounts)


@pytest.fixture
def service_provisioning(
    state_home: Path,
    prepare_kind: PrepareKind,
    prepare_kubectl: Callable[[], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> tuple[Path, list[str], FakeExecute]:
    basic_template["services"] = {
        "crds": {"type": "raw", "manifests": ["https://example.org/crds.yaml"]},
        "operator": {
            "type": "helm",
            "chart": "cnpg",
            "repository": "https://example.org/charts",
            "version": "1",
        },
        "database": {
            "type": "cnpg",
            "database": "app",
            "owner": "app",
            "password": "test",
            "spec": {},
        },
    }
    kind_calls = prepare_kind()
    prepare_kubectl()
    events: list[str] = []
    monkeypatch.setattr(
        supporting,
        "apply_raw_service",
        lambda *_args: events.append("raw"),
    )
    monkeypatch.setattr(helm, "release_statuses", lambda _target: {})
    monkeypatch.setattr(helm, "install_service", lambda *_args: events.append("helm"))
    monkeypatch.setattr(
        cnpg, "apply_cnpg_service", lambda *_args: events.append("cnpg")
    )
    template = write_template(basic_template)
    return template, events, kind_calls


def test_services_follow_template_order(
    service_provisioning: tuple[Path, list[str], FakeExecute],
) -> None:
    template, events, _kind_calls = service_provisioning

    lifecycle.create_environment(template)

    assert events == ["raw", "helm", "cnpg"]


def test_non_deployed_helm_release_fails_without_install(
    service_provisioning: tuple[Path, list[str], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template, events, _kind_calls = service_provisioning
    monkeypatch.setattr(
        helm,
        "release_statuses",
        lambda _target: {("integration", "operator"): "failed"},
    )

    with pytest.raises(ValueError, match="status 'failed'"):
        lifecycle.create_environment(template)

    assert events == ["raw"]


def test_service_failure_stops_provisioning_and_preserves_environment(
    service_provisioning: tuple[Path, list[str], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
    prepare_kind: PrepareKind,
) -> None:
    template, events, _initial_kind_calls = service_provisioning
    kind_calls = prepare_kind(present=True)

    def fail_raw(*_args: object) -> None:
        events.append("raw")
        raise RuntimeError("readiness failed")

    monkeypatch.setattr(supporting, "apply_raw_service", fail_raw)

    with pytest.raises(RuntimeError, match="readiness failed"):
        lifecycle.create_environment(template, allow_reuse=True)

    assert events == ["raw"]
    assert execution_target("integration").kubeconfig.is_file()
    assert not kind_calls.calls_for("kind", "delete")


def test_argo_oci_preflight_checks_credentials_before_kind(
    state_home: Path,
    prepare_kind: PrepareKind,
    monkeypatch: pytest.MonkeyPatch,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> None:
    basic_template["services"] = {
        "argo": {
            "type": "helm",
            "chart": "argo-cd",
            "repository": "https://example.org/charts",
            "version": "1",
            "integration": {
                "type": "argo-cd",
                "oci_repositories": [
                    {
                        "name": "charts",
                        "registry": "ghcr.io",
                        "repository": "org/charts",
                    }
                ],
            },
        }
    }
    calls = prepare_kind()

    def fail_credential(_registry: str) -> tuple[str, str]:
        raise LookupError("missing registry credential")

    monkeypatch.setattr(secrets, "resolve_registry_credential", fail_credential)
    with pytest.raises(LookupError, match="missing registry credential"):
        lifecycle.create_environment(write_template(basic_template))
    assert calls.calls == []


def test_native_kind_mount_collision_fails_before_cluster_lookup(
    deployments_checkout: Path,
    write_bindings: WriteBindings,
    state_home: Path,
    prepare_kind: PrepareKind,
    tmp_path: Path,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> None:
    checkout = deployments_checkout
    write_bindings(repositories={"deployments": str(checkout)})
    [worker] = [
        node
        for node in basic_template["cluster"]["kind"]["nodes"]
        if node["role"] == "worker"
    ]
    worker["extraMounts"] = [
        {"hostPath": str(tmp_path), "containerPath": "/mnt/local-repos/deployments"}
    ]
    basic_template["inputs"] = {"repositories": ["deployments"]}
    basic_template["services"] = {
        "argo": {
            "type": "helm",
            "chart": "argo-cd",
            "repository": "https://example.org/charts",
            "version": "1",
            "integration": {"type": "argo-cd", "repositories": ["deployments"]},
        }
    }
    calls = prepare_kind()
    with pytest.raises(ValueError, match="collides with native Kind extraMount"):
        lifecycle.create_environment(write_template(basic_template))
    assert calls.calls == []


def test_config_maps_and_database_credentials_use_service_namespace(
    state_home: Path,
    prepare_kind: PrepareKind,
    tmp_path: Path,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    fake_execute: FakeExecuteFactory,
) -> None:
    import base64

    (tmp_path / "config.txt").write_text("configuration")
    basic_template["services"] = {
        "helper": {
            "type": "helm",
            "chart": "helper",
            "repository": "https://example.org/charts",
            "version": "1",
            "namespace": "helpers",
            "config_maps_from_file": [
                {"name": "settings", "from_file": {"app.conf": "config.txt"}}
            ],
            "load_db_credentials": {
                "from_secret": "database-login",
                "database": "load",
            },
        }
    }
    prepare_kind()
    kubectl_calls = (
        fake_execute(kubernetes)
        .on(
            "kubectl",
            "--kubeconfig=" + str(execution_target("integration").kubeconfig),
            "--context=kind-zep-dev-integration",
            "get",
            "secret",
            stdout=json.dumps(
                {
                    "data": {
                        key: base64.b64encode(value.encode()).decode()
                        for key, value in {
                            "host": "postgres.helpers",
                            "port": "5432",
                            "username": "user",
                            "password": "private",
                        }.items()
                    }
                }
            ),
        )
        .on("kubectl", stdout="")
    )
    fake_execute(helm).on(
        "helm", "list", stdout="[]", hook=lambda *_: (tmp_path / "config.txt").unlink()
    ).on("helm", "install")
    lifecycle.create_environment(write_template(basic_template))
    applied = [
        content
        for call in kubectl_calls.calls
        if call.args[3:6] == ("apply", "-f", "-")
        and isinstance(content := call.kwargs.get("input"), str)
    ]
    config_map = yaml.safe_load(
        next(value for value in applied if "kind: ConfigMap" in value)
    )
    assert config_map["metadata"]["namespace"] == "helpers"
    assert config_map["data"] == {"app.conf": "configuration"}
    generated = yaml.safe_load(
        next(value for value in applied if "ewb-load-database-config" in value)
    )
    assert generated["metadata"]["namespace"] == "helpers"
    assert (
        json.loads(generated["stringData"]["load-database.json"])["password"]
        == "private"
    )
    assert any(
        entry.kwargs.get("capture_stderr") and entry.kwargs.get("check") is False
        for entry in kubectl_calls.calls
        if entry.kwargs.get("input")
        and "ewb-load-database-config" in str(entry.kwargs["input"])
    )
