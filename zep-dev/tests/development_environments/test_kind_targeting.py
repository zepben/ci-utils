import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.support.execution import FakeExecuteFactory
from zep_dev.development_environments import kind
from zep_dev.development_environments.target import execution_target
from zep_dev.errors import ZepDevError
from zep_dev.shared import CommandResult


@pytest.mark.parametrize("fail", [False, True])
def test_kind_uses_unique_config_and_scoped_kubeconfig(
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    fail: bool,
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    config_paths: list[Path] = []

    def check_create(args: tuple[str, ...], kwargs: dict[str, object]) -> None:
        path = Path(args[args.index("--config") + 1])
        config_paths.append(path)
        assert path.is_file()
        assert path.parent == target.directory
        assert ("--kubeconfig", str(target.kubeconfig)) == args[-2:]
        if not fail:
            target.kubeconfig.write_text("config")
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert env["KUBECONFIG"] == str(target.kubeconfig)

    fake = fake_execute(kind).on(
        "kind",
        "create",
        "cluster",
        hook=check_create,
        raises=subprocess.CalledProcessError(1, ["kind"]) if fail else None,
    )
    config: dict[str, Any] = {
        "kind": "Cluster",
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "nodes": [{"role": "control-plane"}, {"role": "worker"}],
    }
    rendered = kind.render_kind_config(config)
    if fail:
        with pytest.raises(subprocess.CalledProcessError):
            kind.create_cluster(target, rendered)
    else:
        kind.create_cluster(target, rendered)
        assert len(fake.calls_for("kind", "create")) == 1
        assert fake.calls_for("kind", "export") == []
    assert len(config_paths) == 1
    [config_path] = config_paths
    assert not config_path.exists()
    assert all("extraMounts" not in node for node in config["nodes"])


def test_kind_mounts_are_worker_only_and_read_only(tmp_path: Path) -> None:
    config = {
        "kind": "Cluster",
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "nodes": [{"role": "control-plane"}, {"role": "worker"}],
    }
    rendered = kind.render_kind_config(
        config,
        [kind.HostMount(tmp_path, "/mnt/repo", read_only=True)],
    )
    nodes = {node["role"]: node for node in yaml.safe_load(rendered)["nodes"]}
    assert "extraMounts" not in nodes["control-plane"]
    assert nodes["worker"]["extraMounts"] == [
        {"hostPath": str(tmp_path), "containerPath": "/mnt/repo", "readOnly": True}
    ]
    assert all("extraMounts" not in node for node in config["nodes"])


def test_reuse_rejects_wrong_worker_mount_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    mount = kind.HostMount(tmp_path / "repository", "/mnt/repo", read_only=True)
    monkeypatch.setattr(
        kind,
        "kind",
        lambda *_args, **_kwargs: CommandResult(
            0, f"{target.cluster_name}-worker\n", ""
        ),
    )
    monkeypatch.setattr(
        kind,
        "inspect_bind_mounts",
        lambda _worker, **_kwargs: {
            (str(mount.host_path.resolve()), mount.node_path, False)
        },
    )
    with pytest.raises(ZepDevError, match="mounts differ"):
        kind.validate_existing_worker_mounts(target, [mount])


def test_kubeconfig_export_sends_kind_stdout_to_stderr(
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})

    def write_kubeconfig(args: tuple[str, ...], kwargs: dict[str, object]) -> None:
        assert kwargs["capture_stdout"] is True
        path = Path(args[args.index("--kubeconfig") + 1])
        path.write_text("config", encoding="utf-8")

    fake_execute(kind).on(
        "kind",
        "export",
        "kubeconfig",
        stdout="Set kubectl context to kind-zep-dev-integration\n",
        hook=write_kubeconfig,
    )
    kind.export_kubeconfig(target)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Set kubectl context" in captured.err


def test_kind_round_trip_preserves_unmodeled_options_and_native_mounts(
    tmp_path: Path,
) -> None:
    from zep_dev.development_environments.templates import KindConfig

    config = {
        "kind": "Cluster",
        "apiVersion": "kind.x-k8s.io/v1alpha4",
        "networking": {"disableDefaultCNI": True},
        "nodes": [
            {
                "role": "worker",
                "image": "kindest/node:v1",
                "extraMounts": [
                    {
                        "hostPath": "/native",
                        "containerPath": "/data",
                        "selinuxRelabel": True,
                    }
                ],
                "extraPortMappings": [{"containerPort": 8080, "hostPort": 8080}],
            }
        ],
    }
    model = KindConfig.model_validate(config)
    rendered = yaml.safe_load(
        kind.render_kind_config(model, [kind.HostMount(tmp_path, "/added")])
    )
    assert rendered["networking"] == config["networking"]
    worker = rendered["nodes"][0]
    assert worker["image"] == "kindest/node:v1"
    assert worker["extraPortMappings"] == [{"containerPort": 8080, "hostPort": 8080}]
    assert worker["extraMounts"] == [
        {"hostPath": "/native", "containerPath": "/data", "selinuxRelabel": True},
        {"hostPath": str(tmp_path), "containerPath": "/added", "readOnly": False},
    ]
    assert model.model_dump(exclude_unset=True) == config
