from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.support.execution import FakeExecuteFactory
from zep_dev.cli import cli
from zep_dev.development_environments import cli as commands
from zep_dev.development_environments import images, kind, secrets, terraform
from zep_dev.development_environments.target import ExecutionTarget
from zep_dev.errors import ZepDevError

pytestmark = pytest.mark.usefixtures("cli_environment")


def test_create_passes_template_archive_and_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / "template.yaml"
    template.write_text("metadata: {}\n")
    archive = tmp_path / "images.tar"
    seen: list[tuple[Path, bool, Path | None]] = []

    def create(
        path: Path, *, allow_reuse: bool, image_archive: Path | None
    ) -> ExecutionTarget:
        seen.append((path, allow_reuse, image_archive))
        return ExecutionTarget("integration", tmp_path)

    monkeypatch.setattr(commands, "create_environment", create)
    result = CliRunner().invoke(
        cli,
        [
            "environment",
            "create",
            "--template",
            str(template),
            "--allow-reuse",
            "--image-archive",
            str(archive),
        ],
    )
    assert result.exit_code == 0, result.exception
    assert seen == [(template, True, archive)]
    assert result.stdout == ""
    assert "integration ready" in result.stderr


@pytest.mark.parametrize(
    ("clusters", "output"),
    [
        (
            "zep-dev-zeta\nother\nzep-dev-alpha\nzep-dev-Bad\nzep-dev-\n",
            "alpha\nzeta\n",
        ),
        ("", ""),
    ],
)
def test_environment_list(
    fake_execute: FakeExecuteFactory, clusters: str, output: str
) -> None:
    calls = fake_execute(kind).on("kind", "get", "clusters", "--quiet", stdout=clusters)
    result = CliRunner().invoke(cli, ["environment", "list"])
    assert result.exit_code == 0, result.exception
    assert result.stdout == output
    assert result.stderr == ""
    assert len(calls.calls_for("kind", "get", "clusters", "--quiet")) == 1


def test_environment_list_kind_failure(fake_execute: FakeExecuteFactory) -> None:
    fake_execute(kind).on("kind", "get", "clusters", "--quiet", returncode=1)
    result = CliRunner().invoke(cli, ["environment", "list"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "kind" in result.stderr


def test_kubeconfig_prints_only_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = ExecutionTarget("integration", tmp_path)
    monkeypatch.setattr(
        commands, "environment_kubeconfig", lambda _name: target.kubeconfig
    )
    result = CliRunner().invoke(cli, ["environment", "kubeconfig", "integration"])
    assert result.exit_code == 0
    assert result.stdout == f"{target.kubeconfig}\n"
    assert result.stderr == ""


def test_kubeconfig_failure_is_reported_without_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing(_name: str) -> Path:
        raise ZepDevError("Kind cluster 'zep-dev-integration' does not exist")

    monkeypatch.setattr(commands, "environment_kubeconfig", missing)
    result = CliRunner().invoke(cli, ["environment", "kubeconfig", "integration"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Error: Kind cluster 'zep-dev-integration' does not exist" in result.stderr


def test_auxiliary_commands_pass_explicit_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = ExecutionTarget("integration", tmp_path)
    selected: list[str] = []

    def require_environment(name: str) -> ExecutionTarget:
        selected.append(name)
        return target

    def list_images(chosen: ExecutionTarget, _includes: tuple[str, ...]) -> list[str]:
        assert chosen is target
        return ["example/app:1"]

    monkeypatch.setattr(commands, "require_environment", require_environment)
    monkeypatch.setattr(images, "list_images", list_images)
    result = CliRunner().invoke(cli, ["images", "list", "--environment", "integration"])
    assert result.exit_code == 0, result.exception
    assert result.stdout == "example/app:1\n"
    assert selected == ["integration"]


def test_standalone_secrets_preserve_payload_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = ExecutionTarget("integration", tmp_path)
    payload = tmp_path / "secrets.yaml"
    payload.write_text("secrets: []\n")
    calls: list[tuple[object, ...]] = []
    monkeypatch.setattr(commands, "require_environment", lambda _name: target)
    monkeypatch.setattr(
        secrets,
        "create_additional_secrets",
        lambda *args: calls.append(args),
    )
    monkeypatch.setattr(
        secrets,
        "create_image_pull_secret",
        lambda *args: calls.append(args),
    )
    result = CliRunner().invoke(
        cli,
        [
            "secrets",
            "create",
            "--environment",
            "integration",
            "--namespace",
            "test",
            "--ci-secrets-file",
            str(payload),
        ],
    )
    assert result.exit_code == 0, result.exception
    assert len(calls) == 2
    assert (target, "test", payload) in calls
    assert (target, "test") in calls


def test_terraform_uses_selected_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = ExecutionTarget("integration", tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    called: list[tuple[ExecutionTarget, Path, str]] = []
    monkeypatch.setattr(commands, "require_environment", lambda _name: target)
    monkeypatch.setattr(
        terraform,
        "apply_terraform",
        lambda *args: called.append(args),
    )
    result = CliRunner().invoke(
        cli,
        [
            "terraform",
            "apply",
            "--environment",
            "integration",
            "--root",
            str(root),
            "--namespace",
            "test",
        ],
    )
    assert result.exit_code == 0, result.exception
    assert called == [(target, root, "test")]
