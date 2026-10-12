import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.support.execution import FakeExecuteFactory
from zep_dev.development_environments import terraform
from zep_dev.development_environments.target import execution_target
from zep_dev.development_environments.templates import EnvironmentTemplate


def database_template(basic_template: dict[str, Any]) -> EnvironmentTemplate:
    basic_template.update(
        distribution="distribution.yaml",
        services={
            "postgres": {
                "type": "cnpg",
                "namespace": "databases",
                "database": "eas",
                "owner": "eas",
                "password": "private-password",
                "spec": {"instances": 1},
            }
        },
        applications={"eas": {"database": {"service": "postgres"}}},
        inputs={"repositories": ["deployments"]},
    )
    return EnvironmentTemplate.model_validate(basic_template)


def test_runtime_root_targets_provider_and_preserves_state(
    tmp_path: Path, basic_template: dict[str, Any]
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    template = database_template(basic_template)
    deployments = tmp_path / "deployments"
    module = deployments / "terraform/modules/kubernetes/eas-kind-runtime-contract"
    module.mkdir(parents=True)
    databases = terraform.resolve_runtime_databases(template, deployments)
    root = terraform.generate_runtime_root(target, databases)
    state = root / "terraform.tfstate"
    state.write_text("preserve")
    assert root == target.directory / "terraform/runtime"
    config = json.loads((root / "main.tf.json").read_text())
    variables = json.loads((root / "terraform.tfvars.json").read_text())
    assert (
        root / config["module"]["eas_runtime_contract"]["source"]
    ).resolve() == module
    assert variables["kubeconfig"] == str(target.kubeconfig)
    assert variables["context"] == target.context
    assert variables["namespace"] == target.namespace
    assert (
        variables["databases"]["eas"]["host"]
        == "postgres-rw.databases.svc.cluster.local"
    )
    assert variables["databases"]["eas"]["password"] == "private-password"
    assert (root / "terraform.tfvars.json").stat().st_mode & 0o777 == 0o600
    assert (target.directory / "terraform").stat().st_mode & 0o777 == 0o700
    assert root.stat().st_mode & 0o777 == 0o700
    assert "private-password" not in (root / "main.tf.json").read_text()
    template.applications["eas"].database = None
    terraform.generate_runtime_root(
        target, terraform.resolve_runtime_databases(template, None)
    )
    assert state.read_text() == "preserve"
    assert json.loads((root / "main.tf.json").read_text())["module"] == {}


def test_standalone_state_and_subprocess_are_environment_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    monkeypatch.setenv("KUBECONFIG", "/hostile/default")
    monkeypatch.setenv("KUBE_CONFIG_PATH", "/hostile/provider")
    monkeypatch.setenv("TF_VAR_namespace", "production")
    root = tmp_path / "root"
    root.mkdir()
    first = execution_target("first", environ={"XDG_STATE_HOME": str(tmp_path)})
    second = execution_target("second", environ={"XDG_STATE_HOME": str(tmp_path)})
    seen: list[str] = []

    def check_env(_args: tuple[str, ...], kwargs: dict[str, object]) -> None:
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert env["KUBECONFIG"] in {str(first.kubeconfig), str(second.kubeconfig)}
        assert env["KUBE_CONFIG_PATH"] == env["KUBECONFIG"]
        assert "TF_VAR_namespace" not in env
        for key in ("HOME", "TF_DATA_DIR", "TF_CLI_CONFIG_FILE"):
            assert Path(env[key]).exists()
        seen.append(env["KUBECONFIG"])

    fake = (
        fake_execute(terraform)
        .on("terraform", f"-chdir={root}", "init", hook=check_env)
        .on("terraform", f"-chdir={root}", "apply", hook=check_env)
    )
    for target in (first, second):
        state = terraform.apply_terraform(target, root, "test")
        assert state == target.standalone_state(root, "test")
        assert state.parent.stat().st_mode & 0o777 == 0o700
        assert (target.directory / "terraform").stat().st_mode & 0o777 == 0o700
    assert first.standalone_state(root, "test") != second.standalone_state(root, "test")
    assert seen == [str(first.kubeconfig)] * 2 + [str(second.kubeconfig)] * 2
    assert os.environ["KUBECONFIG"] == "/hostile/default"
    assert len(fake.calls_for("terraform", f"-chdir={root}", "apply")) == 2


def test_destroy_cleans_only_selected_standalone_state(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    first = execution_target("first", environ={"XDG_STATE_HOME": str(tmp_path)})
    second = execution_target("second", environ={"XDG_STATE_HOME": str(tmp_path)})
    first_state = first.standalone_state(root, "test")
    second_state = second.standalone_state(root, "test")
    for state in (first_state, second_state):
        state.parent.mkdir(parents=True)
        state.write_text("{}")
    runtime = terraform.runtime_state(first)
    runtime.parent.mkdir(parents=True)
    runtime.write_text("{}")
    fake_execute(terraform).on("terraform", f"-chdir={root}", "init").on(
        "terraform", f"-chdir={root}", "destroy"
    )
    terraform.destroy_terraform(first, root, "test")
    assert not first_state.parent.exists()
    assert second_state.is_file()
    assert runtime.is_file()
    with pytest.raises(FileNotFoundError, match="state does not exist"):
        terraform.destroy_terraform(first, root, "test")


def test_destroy_failure_preserves_state(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = execution_target("first", environ={"XDG_STATE_HOME": str(tmp_path)})
    state = target.standalone_state(root, "test")
    state.parent.mkdir(parents=True)
    state.write_text("preserve")
    fake_execute(terraform).on("terraform", f"-chdir={root}", "init").on(
        "terraform",
        f"-chdir={root}",
        "destroy",
        raises=subprocess.CalledProcessError(1, ["terraform", "destroy"]),
    )
    with pytest.raises(subprocess.CalledProcessError):
        terraform.destroy_terraform(target, root, "test")
    assert state.read_text() == "preserve"


def test_database_repository_requires_native_wrapper(
    basic_template: dict[str, Any], tmp_path: Path
) -> None:
    template = database_template(basic_template)
    with pytest.raises(FileNotFoundError, match="eas-kind-runtime-contract"):
        terraform.resolve_runtime_databases(template, tmp_path)
    wrapper = tmp_path / "terraform/modules/kubernetes/eas-kind-runtime-contract"
    wrapper.mkdir(parents=True)
    [database] = terraform.resolve_runtime_databases(template, tmp_path)
    assert database.module == wrapper


def test_runtime_preflight_does_not_create_files_for_missing_wrapper(
    tmp_path: Path, basic_template: dict[str, Any]
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    template = database_template(basic_template)
    with pytest.raises(FileNotFoundError, match="runtime wrapper"):
        terraform.resolve_runtime_databases(template, tmp_path / "deployments")
    assert not target.directory.exists()


def test_standalone_state_symlink_is_rejected_before_terraform(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    target = execution_target("first", environ={"XDG_STATE_HOME": str(tmp_path)})
    state = target.standalone_state(root, "test")
    state.parent.mkdir(parents=True)
    outside = tmp_path / "outside.tfstate"
    outside.write_text("preserve")
    state.symlink_to(outside)
    fake = fake_execute(terraform)
    with pytest.raises(ValueError, match="symlink"):
        terraform.apply_terraform(target, root, "test")
    with pytest.raises(ValueError, match="symlink"):
        terraform.destroy_terraform(target, root, "test")
    assert fake.calls == []
    assert outside.read_text() == "preserve"


def test_runtime_applies_empty_module_set_when_state_remains(
    tmp_path: Path, basic_template: dict[str, Any], fake_execute: FakeExecuteFactory
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    template = EnvironmentTemplate.model_validate(basic_template)
    fake = (
        fake_execute(terraform)
        .on("terraform", f"-chdir={target.runtime_root}", "init")
        .on("terraform", f"-chdir={target.runtime_root}", "apply")
    )
    databases = terraform.resolve_runtime_databases(template, None)
    assert terraform.apply_runtime(target, databases) is None
    assert fake.calls == []
    state = terraform.runtime_state(target)
    state.parent.mkdir(parents=True)
    state.write_text("preserve")
    assert terraform.apply_runtime(target, databases) == state
    assert (
        json.loads((target.runtime_root / "main.tf.json").read_text())["module"] == {}
    )
    assert (
        len(fake.calls_for("terraform", f"-chdir={target.runtime_root}", "apply")) == 1
    )
    assert state.read_text() == "preserve"
