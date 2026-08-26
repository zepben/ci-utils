import subprocess
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

import click
import pytest

from _fake_execute import FakeExecute
from zep_dev.commands.terraform import commands as terraform_module


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


def test_apply_and_destroy_share_state(
    terraform_root: Path,
    state_root: Path,
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    namespace = "test-namespace"
    absolute_root = terraform_root.resolve()
    state = terraform_module.terraform_state_path(absolute_root, namespace)
    chdir = f"-chdir={absolute_root}"

    def write_state(
        _args: tuple[str, ...],
        _kwargs: dict[str, object],
    ) -> None:
        state.parent.mkdir(parents=True)
        state.write_text("{}")

    fake = (
        fake_execute(terraform_module)
        .on("terraform", chdir, "init")
        .on("terraform", chdir, "apply", hook=write_state)
        .on("terraform", chdir, "destroy")
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
