import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import ANY, call

import click
import pytest

from _fake_execute import FakeExecute
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


def assert_terraform_environment(
    _args: tuple[str, ...],
    kwargs: dict[str, object],
) -> None:
    environment = kwargs.get("env")
    assert isinstance(environment, dict)
    assert set(environment) == TERRAFORM_ENVIRONMENT_KEYS
    assert environment.get("PATH") == PARENT_ENVIRONMENT.get("PATH")
    assert environment.get("KUBECONFIG") == str(KUBECONF_PATH)
    assert environment.get("KUBE_CONFIG_PATH") == str(KUBECONF_PATH)

    for name in ISOLATED_PATH_VARIABLES:
        path = environment.get(name)
        assert isinstance(path, str)
        assert path != PARENT_ENVIRONMENT.get(name)
        assert Path(path).exists()


@pytest.fixture
def terraform_root(tmp_path: Path) -> Path:
    root = tmp_path / "terraform"
    root.mkdir()
    return root


@pytest.fixture
def state_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "states"
    monkeypatch.setattr(terraform_module, "STATE_ROOT", root)
    monkeypatch.delenv("TF_DATA_DIR", raising=False)
    return root


def test_apply_and_destroy_share_state_with_isolated_environment(
    terraform_root: Path,
    state_root: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    namespace = "test-namespace"
    absolute_root = terraform_root.resolve()
    state = terraform_module.terraform_state_path(absolute_root, namespace)
    chdir = f"-chdir={absolute_root}"

    for name, value in PARENT_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)

    def write_state(
        args: tuple[str, ...],
        kwargs: dict[str, object],
    ) -> None:
        assert_terraform_environment(args, kwargs)
        state.parent.mkdir(parents=True)
        state.write_text("{}")

    fake = (
        fake_execute(terraform_module)
        .on("terraform", chdir, "init", hook=assert_terraform_environment)
        .on("terraform", chdir, "apply", hook=write_state)
        .on("terraform", chdir, "destroy", hook=assert_terraform_environment)
    )

    terraform_module.apply_terraform(terraform_root, namespace)
    assert state.is_file()

    unrelated_state = state_root / "unrelated" / "terraform.tfstate"
    unrelated_state.parent.mkdir()
    unrelated_state.write_text("{}")

    terraform_module.destroy_terraform(terraform_root, namespace)

    assert not state.parent.exists()
    assert unrelated_state.is_file()
    init_call = call(
        "terraform",
        chdir,
        "init",
        "-backend=false",
        "-input=false",
        "-lockfile=readonly",
        env=ANY,
    )
    assert fake.calls == [
        init_call,
        call(
            "terraform",
            chdir,
            "apply",
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={namespace}",
            env=ANY,
        ),
        init_call,
        call(
            "terraform",
            chdir,
            "destroy",
            "-input=false",
            "-auto-approve",
            f"-state={state}",
            f"-var=namespace={namespace}",
            env=ANY,
        ),
    ]


def test_destroy_failure_preserves_state(
    terraform_root: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    namespace = "test-namespace"
    absolute_root = terraform_root.resolve()
    state = terraform_module.terraform_state_path(absolute_root, namespace)
    state.parent.mkdir(parents=True)
    state.write_text("{}")
    chdir = f"-chdir={absolute_root}"
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

    assert state.is_file()


def test_destroy_requires_existing_state(
    terraform_root: Path,
    state_root: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    fake = fake_execute(terraform_module)

    with pytest.raises(click.ClickException, match="state does not exist"):
        terraform_module.destroy_terraform(terraform_root, "test-namespace")

    assert not state_root.exists()
    assert fake.calls == []
