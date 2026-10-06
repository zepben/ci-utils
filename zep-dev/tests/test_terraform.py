import os
import subprocess
from pathlib import Path

import click
import pytest

from _fake_execute import FakeExecuteFactory
from zep_dev.commands.terraform import commands as terraform_module
from zep_dev.k8s import KUBECONF_PATH

PARENT_ENVIRONMENT = {
    "PATH": "/trusted/bin",
    "HOME": "/real/home",
    "KUBECONFIG": "/real/kubeconfig",
    "KUBE_CONFIG_PATH": "/real/provider-kubeconfig",
    "TF_DATA_DIR": "/real/terraform-data",
    "TF_CLI_CONFIG_FILE": "/real/terraformrc",
    "AWS_SECRET_ACCESS_KEY": "secret",
    "TF_VAR_namespace": "production",
    "SSH_AUTH_SOCK": "/real/ssh-agent",
}
TERRAFORM_ENVIRONMENT_KEYS = {
    "PATH",
    "KUBECONFIG",
    "KUBE_CONFIG_PATH",
    "HOME",
    "TF_DATA_DIR",
    "TF_CLI_CONFIG_FILE",
}
ISOLATED_PATH_VARIABLES = ("HOME", "TF_DATA_DIR", "TF_CLI_CONFIG_FILE")


@pytest.fixture
def terraform_root(tmp_path: Path) -> Path:
    root = tmp_path / "terraform"
    root.mkdir()
    return root


@pytest.fixture
def parent_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in PARENT_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


def assert_terraform_environment(
    _args: tuple[str, ...], kwargs: dict[str, object]
) -> None:
    environment = kwargs["env"]
    assert isinstance(environment, dict)
    assert set(environment) == TERRAFORM_ENVIRONMENT_KEYS
    assert environment["PATH"] == PARENT_ENVIRONMENT["PATH"]
    assert environment["KUBECONFIG"] == str(KUBECONF_PATH)
    assert environment["KUBE_CONFIG_PATH"] == str(KUBECONF_PATH)
    assert os.environ["KUBECONFIG"] == PARENT_ENVIRONMENT["KUBECONFIG"]
    assert os.environ["KUBE_CONFIG_PATH"] == PARENT_ENVIRONMENT["KUBE_CONFIG_PATH"]
    for name in ISOLATED_PATH_VARIABLES:
        path = environment[name]
        assert path != PARENT_ENVIRONMENT[name]
        assert Path(path).exists()


@pytest.mark.parametrize("operation", ["apply", "destroy"])
def test_terraform_commands_use_isolated_environment(
    terraform_root: Path,
    state_root: Path,
    parent_environment: None,
    fake_execute: FakeExecuteFactory,
    operation: str,
) -> None:
    state = terraform_module.terraform_state_path(terraform_root, "test-namespace")
    if operation == "destroy":
        state.parent.mkdir(parents=True)
        state.write_text("{}")
    chdir = f"-chdir={terraform_root}"
    fake = (
        fake_execute(terraform_module)
        .on("terraform", chdir, "init", hook=assert_terraform_environment)
        .on("terraform", chdir, operation, hook=assert_terraform_environment)
    )

    command = (
        terraform_module.apply_terraform
        if operation == "apply"
        else terraform_module.destroy_terraform
    )
    command(terraform_root, "test-namespace")

    assert len(fake.calls_for("terraform", chdir, "init")) == 1
    assert len(fake.calls_for("terraform", chdir, operation)) == 1


def test_apply_and_destroy_share_state(
    terraform_root: Path, state_root: Path, fake_execute: FakeExecuteFactory
) -> None:
    namespace = "test-namespace"
    state = terraform_module.terraform_state_path(terraform_root, namespace)
    chdir = f"-chdir={terraform_root}"

    def write_state(args: tuple[str, ...], kwargs: dict[str, object]) -> None:
        state.write_text("{}")

    fake = (
        fake_execute(terraform_module)
        .on("terraform", chdir, "init")
        .on("terraform", chdir, "apply", hook=write_state)
        .on("terraform", chdir, "destroy")
    )

    terraform_module.apply_terraform(terraform_root, namespace)
    assert state.is_file()
    unrelated = state_root / "unrelated" / "terraform.tfstate"
    unrelated.parent.mkdir()
    unrelated.write_text("{}")

    terraform_module.destroy_terraform(terraform_root, namespace)

    assert not state.parent.exists()
    assert unrelated.is_file()
    assert [command.args[:3] for command in fake.calls] == [
        ("terraform", chdir, "init"),
        ("terraform", chdir, "apply"),
        ("terraform", chdir, "init"),
        ("terraform", chdir, "destroy"),
    ]
    for command in fake.calls_for("terraform", chdir, "init"):
        assert {"-backend=false", "-input=false"} <= set(command.args)
    for operation in ("apply", "destroy"):
        args = fake.calls_for("terraform", chdir, operation)[0].args
        assert {
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={namespace}",
        } <= set(args)


def test_terraform_init_uses_lockfile_readonly_when_lock_present(
    terraform_root: Path, state_root: Path, fake_execute: FakeExecuteFactory
) -> None:
    (terraform_root / ".terraform.lock.hcl").write_text("# lock\n", encoding="utf-8")
    chdir = f"-chdir={terraform_root}"
    fake = (
        fake_execute(terraform_module)
        .on("terraform", chdir, "init")
        .on("terraform", chdir, "apply")
    )

    terraform_module.apply_terraform(terraform_root, "test-namespace")

    init_args = fake.calls_for("terraform", chdir, "init")[0].args
    assert "-lockfile=readonly" in init_args


def test_destroy_failure_preserves_state(
    terraform_root: Path, state_root: Path, fake_execute: FakeExecuteFactory
) -> None:
    namespace = "test-namespace"
    state = terraform_module.terraform_state_path(terraform_root, namespace)
    state.parent.mkdir(parents=True)
    state.write_text("{}")
    chdir = f"-chdir={terraform_root}"
    (
        fake_execute(terraform_module)
        .on("terraform", chdir, "init")
        .on(
            "terraform",
            chdir,
            "destroy",
            raises=subprocess.CalledProcessError(1, ["terraform", "destroy"]),
        )
    )

    with pytest.raises(subprocess.CalledProcessError):
        terraform_module.destroy_terraform(terraform_root, namespace)

    assert state.read_text() == "{}"


def test_destroy_requires_existing_state(
    terraform_root: Path, state_root: Path, fake_execute: FakeExecuteFactory
) -> None:
    fake = fake_execute(terraform_module)

    with pytest.raises(click.ClickException, match="state does not exist"):
        terraform_module.destroy_terraform(terraform_root, "test-namespace")

    assert not state_root.exists()
    assert fake.calls == []


def test_apply_uses_explicit_profile_state_without_standalone_state_directory(
    terraform_root: Path, state_root: Path, fake_execute: FakeExecuteFactory
) -> None:
    state = terraform_root / "terraform.tfstate"
    chdir = f"-chdir={terraform_root}"
    fake = (
        fake_execute(terraform_module)
        .on("terraform", chdir, "init")
        .on("terraform", chdir, "apply")
    )

    terraform_module.apply_terraform(terraform_root, "platform", state=state)

    args = fake.calls_for("terraform", chdir, "apply")[0].args
    assert f"-state={state}" in args
    assert not state_root.exists()
