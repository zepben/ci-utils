import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from tests.support.execution import FakeExecuteFactory, option_value
from zep_dev.development_environments import helm, kubernetes
from zep_dev.development_environments import target as targets


def test_two_targets_have_disjoint_absolute_identifiers_and_state(
    tmp_path: Path,
) -> None:
    first = targets.execution_target(
        "integration", environ={"XDG_STATE_HOME": str(tmp_path)}
    )
    second = targets.execution_target(
        "test-cluster", environ={"XDG_STATE_HOME": str(tmp_path)}
    )
    assert first.cluster_name == "zep-dev-integration"
    assert first.context == "kind-zep-dev-integration"
    assert first.namespace == "integration"
    assert first.kubeconfig == tmp_path / "zep-dev/environments/integration/kubeconfig"
    assert first.runtime_root == first.directory / "terraform/runtime"
    assert second.cluster_name == "zep-dev-test-cluster"
    assert first.directory != second.directory
    root = tmp_path / "same-root"
    assert first.standalone_state(root, "test") != second.standalone_state(root, "test")
    assert first.standalone_state(root, "test") != first.standalone_state(root, "other")
    assert first.standalone_state(root, "test").is_absolute()


def test_invalid_name_fails_before_path_derivation(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        targets.execution_target("../escape", environ={"XDG_STATE_HOME": str(tmp_path)})
    assert list(tmp_path.iterdir()) == []


def test_empty_state_home_uses_home_and_relative_state_home_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    target = targets.execution_target("test", environ={"XDG_STATE_HOME": ""})
    assert target.directory == tmp_path / ".local/state/zep-dev/environments/test"
    with pytest.raises(ValueError, match="XDG_STATE_HOME"):
        targets.execution_target("test", environ={"XDG_STATE_HOME": "relative"})


def test_kubernetes_and_helm_ignore_hostile_inherited_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    monkeypatch.setenv("KUBECONFIG", "/hostile/default")
    monkeypatch.setenv("KUBE_CONFIG_PATH", "/hostile/provider")
    monkeypatch.setenv("HELM_KUBECONTEXT", "production")
    monkeypatch.setenv("HELM_KUBEAPISERVER", "https://production")
    monkeypatch.setenv("HELM_NAMESPACE", "production")
    monkeypatch.setenv("KUBERNETES_MASTER", "https://production")
    first = targets.execution_target("first", environ={"XDG_STATE_HOME": str(tmp_path)})
    second = targets.execution_target(
        "second", environ={"XDG_STATE_HOME": str(tmp_path)}
    )
    kubectl_calls = fake_execute(kubernetes).on("kubectl")
    helm_calls = fake_execute(helm).on("helm")
    for target in (first, second):
        kubernetes.kubectl(target, "get", "namespace")
        helm.helm(target, "list", "--all-namespaces")
    for target, call in zip((first, second), kubectl_calls.calls, strict=True):
        assert f"--kubeconfig={target.kubeconfig}" in call.args
        assert f"--context={target.context}" in call.args
        env = call.kwargs["env"]
        assert isinstance(env, dict)
        assert env["KUBECONFIG"] == str(target.kubeconfig)
        assert "KUBERNETES_MASTER" not in env
    for target, call in zip((first, second), helm_calls.calls, strict=True):
        assert option_value(call.args, "--kubeconfig") == str(target.kubeconfig)
        assert option_value(call.args, "--kube-context") == target.context
        env = call.kwargs["env"]
        assert isinstance(env, dict)
        assert "HELM_KUBECONTEXT" not in env
        assert "HELM_KUBEAPISERVER" not in env
        assert "HELM_NAMESPACE" not in env
    assert os.environ["KUBECONFIG"] == "/hostile/default"
    assert os.environ["KUBE_CONFIG_PATH"] == "/hostile/provider"
    assert os.environ["HELM_KUBECONTEXT"] == "production"


def test_private_write_preserves_mode_and_replaces_content(tmp_path: Path) -> None:
    path = tmp_path / "owned" / "secret.json"
    targets.private_write(path, "old")
    targets.private_write(path, "new")
    assert path.read_text() == "new"
    assert path.stat().st_mode & 0o777 == 0o600
    assert path.parent.stat().st_mode & 0o777 == 0o700
    assert list(path.parent.iterdir()) == [path]


def test_private_write_removes_temporary_file_on_replace_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "owned" / "secret.json"
    targets.private_write(destination, "preserve")
    original_replace = Path.replace

    def fail_replace(path: Path, target: Path) -> Path:
        if target == destination:
            raise OSError("injected replace failure")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        targets.private_write(destination, "new")
    assert destination.read_text() == "preserve"
    assert list(destination.parent.iterdir()) == [destination]


def test_private_directory_rejects_symlink_to_external_data(tmp_path: Path) -> None:
    outside = tmp_path / "external"
    outside.mkdir()
    outside.chmod(0o755)
    owned = tmp_path / "owned"
    owned.symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        targets.private_directory(owned)
    assert outside.stat().st_mode & 0o777 != 0o700
