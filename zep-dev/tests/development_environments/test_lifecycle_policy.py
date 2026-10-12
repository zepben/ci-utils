import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import Mock, call, create_autospec

import pytest

from tests.support.kind import FakeKind
from zep_dev.development_environments import (
    helm,
    kind,
    kubernetes,
    lifecycle,
    local_inputs,
    manifests,
    secrets,
    terraform,
)
from zep_dev.development_environments.chart_sources import VersionChartRef
from zep_dev.development_environments.target import (
    ExecutionTarget,
    execution_target,
)
from zep_dev.development_environments.templates import EnvironmentTemplate


@pytest.fixture
def kind_runtime(monkeypatch: pytest.MonkeyPatch, state_home: Path) -> FakeKind:
    runtime = FakeKind()
    for name in (
        "cluster_exists",
        "create_cluster",
        "export_kubeconfig",
        "delete_cluster",
        "validate_existing_worker_mounts",
    ):
        monkeypatch.setattr(kind, name, getattr(runtime, name))
    return runtime


@pytest.fixture
def creation_plan(
    basic_template: dict[str, Any], state_home: Path, monkeypatch: pytest.MonkeyPatch
) -> lifecycle.CreationPlan:
    plan = lifecycle.CreationPlan(
        template=EnvironmentTemplate.model_validate(basic_template),
        target=execution_target("integration"),
        inputs=local_inputs.ResolvedInputs(
            mounts={}, repositories={}, secrets={}, argo_repositories={}
        ),
        mounts=(),
        kind_config=kind.render_kind_config(basic_template["cluster"]["kind"]),
        charts=(),
        config_maps={},
        application_manifests=(),
        runtime_databases=(),
    )
    monkeypatch.setattr(lifecycle, "preflight", lambda *_args: plan)
    return plan


@pytest.fixture
def provisioning(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """Record integration effects, retaining their real signatures."""
    effects = Mock()
    for module, name in (
        (kubernetes, "ensure_namespace"),
        (kubernetes, "apply_builtin_storage_classes"),
        (helm, "install_applications"),
        (terraform, "apply_runtime"),
        (manifests, "apply_application_manifests"),
        (secrets, "create_image_pull_secret"),
    ):
        effect = create_autospec(
            getattr(module, name),
            return_value=None,
        )
        monkeypatch.setattr(module, name, effect)
        effects.attach_mock(effect, name)
    return effects


@pytest.fixture
def application_plan(
    creation_plan: lifecycle.CreationPlan,
    basic_template: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> lifecycle.CreationPlan:
    basic_template.update(
        distribution="distribution.yaml",
        applications={"eas": {"values": {"replicas": 1}}},
    )
    plan = replace(
        creation_plan,
        template=EnvironmentTemplate.model_validate(basic_template),
        charts=(VersionChartRef(name="eas", version="1.0.0", source="version"),),
        application_manifests=(tmp_path / "application.yaml",),
    )
    monkeypatch.setattr(lifecycle, "preflight", lambda *_args: plan)
    return plan


def test_existing_environment_is_refused_before_provisioning(
    creation_plan: lifecycle.CreationPlan, kind_runtime: FakeKind, provisioning: Mock
) -> None:
    target = creation_plan.target
    kind_runtime.clusters.add(target.cluster_name)
    with pytest.raises(FileExistsError, match="allow_reuse"):
        lifecycle.create_environment(Path("template.yaml"))
    assert kind_runtime.events == [("lookup", target)]
    assert provisioning.mock_calls == []
    assert not target.directory.exists()


def test_reuse_exports_kubeconfig_without_creating_cluster(
    creation_plan: lifecycle.CreationPlan, kind_runtime: FakeKind, provisioning: Mock
) -> None:
    target = creation_plan.target
    kind_runtime.clusters.add(target.cluster_name)
    assert (
        lifecycle.create_environment(Path("template.yaml"), allow_reuse=True) == target
    )
    assert kind_runtime.events == [("lookup", target), ("export", target)]
    assert target.kubeconfig.is_file()


def test_stale_files_are_removed_before_cluster_creation(
    creation_plan: lifecycle.CreationPlan,
    kind_runtime: FakeKind,
    provisioning: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = creation_plan.target
    target.directory.mkdir(parents=True)
    stale = target.directory / "old-state"
    stale.write_text("old")
    create = kind_runtime.create_cluster

    def create_after_cleanup(
        chosen: ExecutionTarget,
        config: str,
    ) -> None:
        assert not stale.exists()
        create(chosen, config)

    monkeypatch.setattr(kind, "create_cluster", create_after_cleanup)
    lifecycle.create_environment(Path("template.yaml"))
    assert "Removing stale Environment files" in capsys.readouterr().err
    assert kind_runtime.events == [("lookup", target), ("create", target)]


@pytest.mark.parametrize(
    "phase", ["apply_runtime", "install_applications"], ids=["runtime", "applications"]
)
def test_provisioning_failure_preserves_partial_environment(
    application_plan: lifecycle.CreationPlan,
    kind_runtime: FakeKind,
    provisioning: Mock,
    phase: str,
) -> None:
    target = application_plan.target
    state = target.runtime_root / "terraform.tfstate"

    def fail(*_args: object) -> None:
        state.parent.mkdir(parents=True)
        state.write_text("partial")
        raise RuntimeError("provisioning failed")

    getattr(provisioning, phase).side_effect = fail
    with pytest.raises(RuntimeError, match="provisioning failed"):
        lifecycle.create_environment(Path("template.yaml"))
    assert target.cluster_name in kind_runtime.clusters
    assert target.kubeconfig.is_file()
    assert state.read_text() == "partial"
    assert all(operation != "delete" for operation, _target in kind_runtime.events)


def test_cluster_lookup_failure_preserves_stale_files(
    creation_plan: lifecycle.CreationPlan, kind_runtime: FakeKind, provisioning: Mock
) -> None:
    target = creation_plan.target
    target.directory.mkdir(parents=True)
    state = target.directory / "terraform.tfstate"
    state.write_text("retain")
    kind_runtime.fail_at = "lookup"
    with pytest.raises(RuntimeError, match="lookup failed"):
        lifecycle.create_environment(Path("template.yaml"))
    assert state.read_text() == "retain"
    assert kind_runtime.events == [("lookup", target)]
    assert provisioning.mock_calls == []


def test_stale_cleanup_failure_stops_cluster_creation(
    creation_plan: lifecycle.CreationPlan,
    kind_runtime: FakeKind,
    provisioning: Mock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = creation_plan.target
    target.directory.mkdir(parents=True)

    def fail_cleanup(_path: Path) -> None:
        raise OSError("cleanup failed")

    monkeypatch.setattr(shutil, "rmtree", fail_cleanup)
    with pytest.raises(OSError, match="cleanup failed"):
        lifecycle.create_environment(Path("template.yaml"))
    assert target.directory.exists()
    assert kind_runtime.events == [("lookup", target)]
    assert provisioning.mock_calls == []


def test_reuse_checks_worker_mounts_before_export(
    creation_plan: lifecycle.CreationPlan,
    kind_runtime: FakeKind,
    provisioning: Mock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    target = creation_plan.target
    plan = replace(creation_plan, mounts=(kind.HostMount(tmp_path, "/data"),))
    monkeypatch.setattr(lifecycle, "preflight", lambda *_args: plan)
    kind_runtime.clusters.add(target.cluster_name)
    kind_runtime.fail_at = "mounts"
    with pytest.raises(RuntimeError, match="mounts failed"):
        lifecycle.create_environment(Path("template.yaml"), allow_reuse=True)
    assert kind_runtime.events == [("lookup", target), ("mounts", target)]
    assert provisioning.mock_calls == []


def test_runtime_precedes_manifests_and_application_install(
    application_plan: lifecycle.CreationPlan,
    kind_runtime: FakeKind,
    provisioning: Mock,
) -> None:
    lifecycle.create_environment(Path("template.yaml"))
    target = application_plan.target
    ordered = [
        entry
        for entry in provisioning.mock_calls
        if entry[0]
        in {"apply_runtime", "apply_application_manifests", "install_applications"}
    ]
    assert ordered == [
        call.apply_runtime(target, application_plan.runtime_databases),
        call.apply_application_manifests(
            target, application_plan.application_manifests
        ),
        call.install_applications(
            target, application_plan.charts, {"eas": {"replicas": 1}}
        ),
    ]


def test_destroy_failure_preserves_owned_files(
    state_home: Path, kind_runtime: FakeKind
) -> None:
    target = execution_target("integration")
    target.directory.mkdir(parents=True)
    state = target.directory / "terraform.tfstate"
    state.write_text("important")
    kind_runtime.clusters.add(target.cluster_name)
    kind_runtime.fail_at = "delete"
    with pytest.raises(RuntimeError, match="delete failed"):
        lifecycle.destroy_environment("integration")
    assert state.read_text() == "important"
    assert kind_runtime.events == [("lookup", target), ("delete", target)]


def test_destroy_removes_owned_files_and_preserves_external_inputs(
    state_home: Path,
    kind_runtime: FakeKind,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = execution_target("integration")
    target.runtime_root.mkdir(parents=True)
    (target.runtime_root / "terraform.tfstate").write_text("runtime")
    standalone = target.directory / "terraform/standalone/state"
    standalone.parent.mkdir(parents=True)
    standalone.write_text("standalone")
    external = [
        tmp_path / name
        for name in ("credentials.env", "template.yaml", "distribution.yaml")
    ]
    for directory in (tmp_path / "checkout", tmp_path / "mount"):
        directory.mkdir()
        external.append(directory / "sentinel")
    other = execution_target("other")
    other.directory.mkdir(parents=True)
    external.append(other.directory / "terraform.tfstate")
    for path in external:
        path.write_text("preserve")
    kind_runtime.clusters.add(target.cluster_name)
    delete = kind_runtime.delete_cluster

    def delete_before_cleanup(chosen: ExecutionTarget) -> None:
        assert chosen.directory.exists()
        delete(chosen)

    def unexpected_preflight(*_args: object) -> None:
        raise AssertionError("destroy must not resolve Template or Bindings")

    monkeypatch.setattr(kind, "delete_cluster", delete_before_cleanup)
    monkeypatch.setattr(lifecycle, "preflight", unexpected_preflight)
    lifecycle.destroy_environment("integration")
    lifecycle.destroy_environment("integration")
    assert not target.directory.exists()
    assert target.cluster_name not in kind_runtime.clusters
    assert [path.read_text() for path in external] == ["preserve"] * len(external)
    assert kind_runtime.events == [
        ("lookup", target),
        ("delete", target),
        ("lookup", target),
    ]


def test_kubeconfig_is_exported_once_for_live_environment(
    state_home: Path, kind_runtime: FakeKind
) -> None:
    target = execution_target("integration")
    kind_runtime.clusters.add(target.cluster_name)
    assert lifecycle.environment_kubeconfig("integration") == target.kubeconfig
    assert target.kubeconfig.is_file()
    assert lifecycle.environment_kubeconfig("integration") == target.kubeconfig
    assert kind_runtime.events == [
        ("lookup", target),
        ("export", target),
        ("lookup", target),
    ]


def test_stale_kubeconfig_does_not_make_absent_cluster_valid(
    state_home: Path, kind_runtime: FakeKind
) -> None:
    target = execution_target("integration")
    target.directory.mkdir(parents=True)
    target.kubeconfig.write_text("stale")
    with pytest.raises(FileNotFoundError, match="does not exist"):
        lifecycle.environment_kubeconfig("integration")
    assert target.kubeconfig.read_text() == "stale"
    assert kind_runtime.events == [("lookup", target)]
