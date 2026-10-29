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
from zep_dev.errors import ZepDevError


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
            },
            "hcs-postgres": {
                "type": "cnpg",
                "database": "hcs",
                "databases": {"input": {}},
                "owner": "hcs",
                "password": "input-password",
                "spec": {"instances": 1},
            },
        },
        applications={
            "eas": {
                "databases": {
                    "primary": {"service": "postgres", "database": "eas"},
                    "opendss_input": {"service": "hcs-postgres", "database": "input"},
                }
            }
        },
    )
    return EnvironmentTemplate.model_validate(basic_template)


def test_runtime_root_targets_provider_and_preserves_state(
    tmp_path: Path, basic_template: dict[str, Any]
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    template = database_template(basic_template)
    module = tmp_path / "evolve-app-server/helm/charts/eas/kind-runtime-contract"
    module.mkdir(parents=True)
    applications = terraform.resolve_runtime_applications(
        target, template, {"eas": module}
    )
    root = terraform.generate_runtime_root(target, applications)
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
        variables["databases"]["eas"]["primary"]["host"]
        == "postgres-rw.databases.svc.cluster.local"
    )
    assert variables["databases"]["eas"]["primary"]["password"] == "private-password"
    assert variables["databases"]["eas"]["opendss_input"] == {
        "host": "hcs-postgres-rw.integration.svc.cluster.local",
        "port": 5432,
        "name": "input",
        "username": "hcs",
        "password": "input-password",
    }
    assert (
        config["module"]["eas_runtime_contract"]["databases"] == "${var.databases.eas}"
    )
    assert config["variable"]["databases"]["sensitive"] is True
    assert "private-password" not in (root / "main.tf.json").read_text()
    assert "input-password" not in (root / "main.tf.json").read_text()
    template.applications["eas"].databases.clear()
    terraform.generate_runtime_root(
        target, terraform.resolve_runtime_applications(target, template, {})
    )
    assert state.read_text() == "preserve"
    assert "module" not in json.loads((root / "main.tf.json").read_text())


def test_standalone_state_and_subprocess_are_environment_scoped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    monkeypatch.setenv("KUBECONFIG", "/hostile/default")
    monkeypatch.setenv("KUBE_CONFIG_PATH", "/hostile/provider")
    monkeypatch.setenv("TF_VAR_namespace", "production")
    plugins = Path(os.environ["XDG_CACHE_HOME"]) / "zep-dev/terraform-plugins"
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
        assert env["TF_PLUGIN_CACHE_DIR"] == str(plugins)
        seen.append(env["KUBECONFIG"])

    fake = (
        fake_execute(terraform)
        .on("terraform", f"-chdir={root}", "init", hook=check_env)
        .on("terraform", f"-chdir={root}", "apply", hook=check_env)
    )
    for target in (first, second):
        state = terraform.apply_terraform(target, root, "test")
        assert state == target.standalone_state(root, "test")
    assert first.standalone_state(root, "test") != second.standalone_state(root, "test")
    assert seen == [str(first.kubeconfig)] * 2 + [str(second.kubeconfig)] * 2
    assert plugins.is_dir()
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
    with pytest.raises(ZepDevError, match="state does not exist"):
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
    with pytest.raises(ZepDevError, match="symlink"):
        terraform.apply_terraform(target, root, "test")
    with pytest.raises(ZepDevError, match="symlink"):
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
    applications = terraform.resolve_runtime_applications(target, template, {})
    assert terraform.apply_runtime(target, applications) is None
    assert fake.calls == []
    state = terraform.runtime_state(target)
    state.parent.mkdir(parents=True)
    state.write_text("preserve")
    assert terraform.apply_runtime(target, applications) == state
    assert "module" not in json.loads(
        (target.runtime_root / "main.tf.json").read_text()
    )
    assert (
        len(fake.calls_for("terraform", f"-chdir={target.runtime_root}", "apply")) == 1
    )
    assert state.read_text() == "preserve"


@pytest.mark.parametrize("agent", ["/run/user/1000/ssh-agent.sock", None])
def test_terraform_receives_the_ssh_agent_only_when_one_is_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, agent: str | None
) -> None:
    if agent is None:
        monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    else:
        monkeypatch.setenv("SSH_AUTH_SOCK", agent)
    target = execution_target("first", environ={"XDG_STATE_HOME": str(tmp_path)})
    with terraform.terraform_environment(target) as env:
        assert env.get("SSH_AUTH_SOCK") == agent
