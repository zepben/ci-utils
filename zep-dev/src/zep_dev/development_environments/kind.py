"""Kind cluster operations with private, Environment-specific execution files."""

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

import yaml

from zep_dev.development_environments.target import (
    ExecutionTarget,
    kubernetes_environment,
    private_directory,
)
from zep_dev.development_environments.templates import KindConfig, KindMount
from zep_dev.shared import CommandResult, execute


@dataclass(frozen=True)
class HostMount:
    host_path: Path
    node_path: str
    read_only: bool = False


def kind(
    target: ExecutionTarget, *args: str, capture_stdout: bool = False
) -> CommandResult:
    return execute(
        "kind",
        *args,
        capture_stdout=capture_stdout,
        env=kubernetes_environment(target),
    )


def cluster_exists(target: ExecutionTarget) -> bool:
    clusters = kind(target, "get", "clusters", "--quiet", capture_stdout=True)
    return target.cluster_name in clusters.stdout.splitlines()


def list_clusters() -> list[str]:
    """Return cluster names reported by the local Kind provider."""
    result = execute("kind", "get", "clusters", "--quiet", capture_stdout=True)
    return result.stdout.splitlines()


def render_kind_config(
    config: KindConfig | Mapping[str, object], mounts: Sequence[HostMount] = ()
) -> str:
    validated = (
        config
        if isinstance(config, KindConfig)
        else KindConfig.model_validate(dict(config))
    )
    rendered = validated.model_copy(deep=True)
    workers = [node for node in rendered.nodes if node.role == "worker"]
    if mounts and not workers:
        raise ValueError("host mounts require at least one worker node")
    destinations = {mount.node_path for mount in mounts}
    if len(destinations) != len(mounts):
        raise ValueError("worker mount destinations must be unique")
    for worker in workers:
        for native in worker.extraMounts:
            if native.containerPath in destinations:
                raise ValueError(
                    f"worker mount collides with native Kind extraMount: {native.containerPath}"
                )
        if mounts:
            worker.extraMounts = [
                *worker.extraMounts,
                *(
                    KindMount(
                        hostPath=str(mount.host_path),
                        containerPath=mount.node_path,
                        readOnly=mount.read_only,
                    )
                    for mount in mounts
                ),
            ]
    return yaml.safe_dump(
        rendered.model_dump(exclude_unset=True), default_flow_style=False
    )


def create_cluster(target: ExecutionTarget, config: str) -> None:
    private_directory(target.directory)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        prefix="kind-config-",
        suffix=".yaml",
        dir=target.directory,
    ) as file:
        file.write(config)
        file.flush()
        kind(
            target,
            "create",
            "cluster",
            "--name",
            target.cluster_name,
            "--config",
            file.name,
            "--kubeconfig",
            str(target.kubeconfig),
        )
    target.kubeconfig.chmod(0o600)


def export_kubeconfig(target: ExecutionTarget) -> None:
    private_directory(target.directory)
    result = kind(
        target,
        "export",
        "kubeconfig",
        "--name",
        target.cluster_name,
        "--kubeconfig",
        str(target.kubeconfig),
        capture_stdout=True,
    )
    if result.stdout:
        print(result.stdout, file=sys.stderr, end="")
    target.kubeconfig.chmod(0o600)


def delete_cluster(target: ExecutionTarget) -> None:
    kind(target, "delete", "cluster", "--name", target.cluster_name)


def inspect_bind_mounts(worker: str) -> set[tuple[str, str, bool]]:
    result = execute(
        "podman",
        "inspect",
        worker,
        "--format",
        "{{json .Mounts}}",
        skip_resolve=True,
        capture_stdout=True,
    )
    mounts: object = json.loads(result.stdout)
    if not isinstance(mounts, list):
        raise RuntimeError(f"podman inspect returned invalid mounts for {worker}")
    bind_mounts: set[tuple[str, str, bool]] = set()
    for mount in mounts:
        if not isinstance(mount, dict) or mount.get("Type") != "bind":
            continue
        source = mount.get("Source")
        destination = mount.get("Destination")
        writable = mount.get("RW")
        if not isinstance(source, str) or not isinstance(destination, str):
            raise RuntimeError(
                f"podman inspect returned invalid bind mount for {worker}"
            )
        if not isinstance(writable, bool):
            raise RuntimeError(f"podman inspect omitted bind mount mode for {worker}")
        bind_mounts.add((str(Path(source).resolve()), destination, not writable))
    return bind_mounts


def validate_existing_worker_mounts(
    target: ExecutionTarget, mounts: Sequence[HostMount]
) -> None:
    nodes = kind(
        target,
        "get",
        "nodes",
        "--name",
        target.cluster_name,
        capture_stdout=True,
    ).stdout.splitlines()
    workers = [node for node in nodes if not node.endswith("-control-plane")]
    if not workers:
        raise RuntimeError("host mounts require at least one worker node")
    expected = {(str(m.host_path.resolve()), m.node_path, m.read_only) for m in mounts}
    destinations = {node_path for _, node_path, _ in expected}
    for worker in workers:
        actual = {
            pair for pair in inspect_bind_mounts(worker) if pair[1] in destinations
        }
        if actual != expected:
            raise RuntimeError(f"worker {worker} mounts differ from requested mounts")


def load_image_archive(target: ExecutionTarget, archive: Path) -> None:
    if not archive.is_file() or archive.stat().st_size == 0:
        raise ValueError(f"image archive is missing or empty: {archive}")
    kind(target, "load", "image-archive", str(archive), "--name", target.cluster_name)
