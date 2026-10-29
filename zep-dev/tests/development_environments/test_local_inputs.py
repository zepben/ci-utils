from pathlib import Path
from typing import Any

import pytest

from tests.support.git import init_repository
from zep_dev.development_environments.bindings import Bindings, SecretSource
from zep_dev.development_environments.local_inputs import (
    load_bindings,
    resolve_inputs,
)
from zep_dev.development_environments.templates import EnvironmentTemplate


@pytest.fixture
def binding_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.delenv("ZEP_DEV_BINDINGS", raising=False)
    paths = {
        "local": tmp_path / ".zep-dev/bindings.yaml",
        "config": tmp_path / "config/zep-dev/bindings.yaml",
        "explicit": tmp_path / "explicit.yaml",
    }
    for name, path in paths.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"mounts: {{data: /tmp/{name}}}\n")
    return paths


@pytest.mark.parametrize("selected", ["local", "explicit"])
def test_binding_discovery_precedence(
    binding_files: dict[str, Path], monkeypatch: pytest.MonkeyPatch, selected: str
) -> None:
    if selected == "explicit":
        monkeypatch.setenv("ZEP_DEV_BINDINGS", str(binding_files[selected]))

    bindings = load_bindings()

    assert bindings.mounts["data"] == Path("/tmp") / selected


def test_invalid_selected_binding_does_not_fall_back(
    binding_files: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = binding_files["explicit"]
    explicit.write_text("mounts: {data: /tmp/one, data: /tmp/two}\n")
    monkeypatch.setenv("ZEP_DEV_BINDINGS", str(explicit))

    with pytest.raises(ValueError, match="duplicate"):
        load_bindings()


def test_unused_bindings_are_not_resolved(basic_template: dict[str, Any]) -> None:
    template = EnvironmentTemplate.model_validate(basic_template)
    bindings = Bindings.model_validate(
        {
            "mounts": {"unused": "/nonexistent"},
            "secrets": {"unused": {"file": "/nonexistent"}},
        }
    )

    resolved = resolve_inputs(template, bindings)

    assert resolved.mounts == {}
    assert resolved.secrets == {}


@pytest.mark.parametrize("source_kind", ["env", "file"])
@pytest.mark.parametrize("available", [True, False], ids=["available", "missing"])
def test_required_secret_source_is_resolved_or_refused(
    basic_template: dict[str, Any],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_kind: str,
    available: bool,
) -> None:
    basic_template["inputs"] = {"secrets": {"credentials": {"name": "app-credentials"}}}
    template = EnvironmentTemplate.model_validate(basic_template)
    secret_file = tmp_path / "credentials.env"
    if source_kind == "env":
        monkeypatch.delenv("CREDENTIALS", raising=False)
        if available:
            monkeypatch.setenv("CREDENTIALS", "KEY=value")
        source = SecretSource(env="CREDENTIALS")
        error = "missing or empty"
    else:
        if available:
            secret_file.write_text("KEY=value")
        source = SecretSource(file=secret_file)
        error = "unreadable"
    bindings = Bindings(secrets={"credentials": source})

    if available:
        resolved = resolve_inputs(template, bindings)

        assert resolved.secrets == {"credentials": source}
    else:
        with pytest.raises(ValueError, match=error):
            resolve_inputs(template, bindings)


def test_required_mount_must_exist(basic_template: dict[str, Any]) -> None:
    basic_template["cluster"]["mounts"] = [{"slot": "data", "node_path": "/mnt/data"}]
    basic_template["inputs"] = {"mounts": ["data"]}
    template = EnvironmentTemplate.model_validate(basic_template)
    with pytest.raises(ValueError, match="bindings.mounts.data"):
        resolve_inputs(template, Bindings(mounts={"data": Path("/nonexistent")}))


def test_argo_repository_requires_git_top_level(
    basic_template: dict[str, Any], tmp_path: Path
) -> None:
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
    template = EnvironmentTemplate.model_validate(basic_template)
    inside = init_repository(tmp_path / "deployments") / "terraform"
    inside.mkdir()
    bindings = Bindings(repositories={"deployments": inside})
    with pytest.raises(ValueError, match="Git checkout top level"):
        resolve_inputs(template, bindings)
