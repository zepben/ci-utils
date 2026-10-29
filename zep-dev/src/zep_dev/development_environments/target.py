"""Derive platform targets and owned paths from a validated Environment name."""

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import TypeAdapter

from zep_dev.development_environments.names import (
    CLUSTER_PREFIX,
    EnvironmentName,
    KubernetesName,
)

_NAME: TypeAdapter[str] = TypeAdapter(EnvironmentName)
_KUBERNETES_NAME: TypeAdapter[str] = TypeAdapter(KubernetesName)


def environment_name(value: str) -> str:
    """Validate names supplied outside Template parsing, before path construction."""
    return _NAME.validate_python(value)


def kubernetes_name(value: str) -> str:
    return _KUBERNETES_NAME.validate_python(value)


def state_home(environ: Mapping[str, str] | None = None) -> Path:
    variables = os.environ if environ is None else environ
    configured = variables.get("XDG_STATE_HOME")
    base = Path(configured) if configured else Path.home() / ".local" / "state"
    if not base.is_absolute():
        raise ValueError("XDG_STATE_HOME must be an absolute path")
    return base


def cache_home() -> Path:
    configured = os.environ.get("XDG_CACHE_HOME")
    base = Path(configured) if configured else Path.home() / ".cache"
    if not base.is_absolute():
        raise ValueError("XDG_CACHE_HOME must be an absolute path")
    return base


@dataclass(frozen=True)
class ExecutionTarget:
    name: str
    state_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", environment_name(self.name))
        if not self.state_root.is_absolute():
            raise ValueError("Environment state root must be absolute")

    @property
    def cluster_name(self) -> str:
        return f"{CLUSTER_PREFIX}{self.name}"

    @property
    def context(self) -> str:
        return f"kind-{self.cluster_name}"

    @property
    def namespace(self) -> str:
        return self.name

    def namespace_for(self, *overrides: str | None) -> str:
        """The first namespace override given, else the Environment namespace."""
        return next(
            (namespace for namespace in overrides if namespace is not None),
            self.namespace,
        )

    @property
    def directory(self) -> Path:
        return self.state_root / "zep-dev" / "environments" / self.name

    @property
    def kubeconfig(self) -> Path:
        return self.directory / "kubeconfig"

    @property
    def runtime_root(self) -> Path:
        return self.directory / "terraform" / "runtime"

    @property
    def standalone_root(self) -> Path:
        return self.directory / "terraform" / "standalone"

    def standalone_state(self, root: Path, namespace: str) -> Path:
        valid_namespace = kubernetes_name(namespace)
        resolved = root.resolve()
        key = hashlib.sha256(f"{resolved}\0{valid_namespace}".encode()).hexdigest()
        return self.standalone_root / key / "terraform.tfstate"


def execution_target(
    name: str, *, environ: Mapping[str, str] | None = None
) -> ExecutionTarget:
    return ExecutionTarget(name=name, state_root=state_home(environ))


def kubernetes_environment(target: ExecutionTarget) -> dict[str, str]:
    """Child-only settings; inherited defaults cannot redirect a Kubernetes client."""
    child = dict(os.environ)
    for key in tuple(child):
        if key.startswith("HELM_KUBE") or key in {
            "HELM_NAMESPACE",
            "KUBE_CONTEXT",
            "KUBERNETES_MASTER",
        }:
            child.pop(key)
    child["KUBECONFIG"] = str(target.kubeconfig)
    child["KUBE_CONFIG_PATH"] = str(target.kubeconfig)
    return child
