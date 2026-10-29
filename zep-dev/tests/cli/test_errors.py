from pathlib import Path
from subprocess import CalledProcessError

import pytest
from click.testing import CliRunner, Result

from zep_dev.cli import cli
from zep_dev.development_environments import cli as commands
from zep_dev.errors import ZepDevError

pytestmark = pytest.mark.usefixtures("cli_environment")

CLONE_FAILURE = CalledProcessError(
    128, ["git", "clone"], stderr="git@github.com: Permission denied (publickey).\n"
)


def kubeconfig_failing_with(
    monkeypatch: pytest.MonkeyPatch, error: Exception, *options: str
) -> Result:
    def fail(_name: str) -> Path:
        raise error

    monkeypatch.setattr(commands, "environment_kubeconfig", fail)
    return CliRunner().invoke(
        cli, [*options, "environment", "kubeconfig", "integration"]
    )


def test_expected_failure_is_one_message_on_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = ZepDevError("Kind cluster 'zep-dev-integration' does not exist")
    result = kubeconfig_failing_with(monkeypatch, error)
    assert result.exit_code == 1
    assert result.stdout == ""
    assert result.stderr == f"Error: {error}\n"


def test_failed_command_report_includes_its_captured_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = kubeconfig_failing_with(monkeypatch, CLONE_FAILURE)
    assert result.exit_code == 1
    assert "exit status 128" in result.stderr
    assert "Permission denied (publickey)" in result.stderr


def test_verbose_keeps_the_traceback(monkeypatch: pytest.MonkeyPatch) -> None:
    result = kubeconfig_failing_with(monkeypatch, CLONE_FAILURE, "-v")
    assert result.exception is CLONE_FAILURE
