from collections.abc import Sequence
from dataclasses import dataclass, field

from zep_dev.development_environments.kind import HostMount
from zep_dev.development_environments.target import ExecutionTarget


@dataclass
class FakeKind:
    """Record cluster operations without emulating command construction."""

    clusters: set[str] = field(default_factory=set)
    events: list[tuple[str, ExecutionTarget]] = field(default_factory=list)
    fail_at: str | None = None

    def record(self, operation: str, target: ExecutionTarget) -> None:
        self.events.append((operation, target))
        if self.fail_at == operation:
            raise RuntimeError(f"{operation} failed")

    def cluster_exists(self, target: ExecutionTarget) -> bool:
        self.record("lookup", target)
        return target.cluster_name in self.clusters

    def create_cluster(self, target: ExecutionTarget, config: str) -> None:
        self.record("create", target)
        self.clusters.add(target.cluster_name)
        self.write_kubeconfig(target)

    def export_kubeconfig(self, target: ExecutionTarget) -> None:
        self.record("export", target)
        self.write_kubeconfig(target)

    def delete_cluster(self, target: ExecutionTarget) -> None:
        self.record("delete", target)
        self.clusters.remove(target.cluster_name)

    def validate_existing_worker_mounts(
        self, target: ExecutionTarget, mounts: Sequence[HostMount]
    ) -> None:
        self.record("mounts", target)

    @staticmethod
    def write_kubeconfig(target: ExecutionTarget) -> None:
        target.directory.mkdir(parents=True, exist_ok=True)
        target.kubeconfig.write_text("targeted kubeconfig", encoding="utf-8")
