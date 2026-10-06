import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from zep_dev.shared import CommandResult, execute

KUBECONF_PATH = Path("/tmp/kind-k8s-conf.yaml")


@contextmanager
def kube_guard() -> Generator[None]:
    """
    Keep Kubernetes commands on the Kind kubeconfig for this process.

    Do not restore the previous values: concurrent Helm calls must not see
    another thread's original kubeconfig after one call finishes.
    """
    os.environ["KUBECONFIG"] = str(KUBECONF_PATH)
    os.environ["KUBE_CONFIG_PATH"] = str(KUBECONF_PATH)
    yield


def kubectl(
    *args: str,
    capture_stdout: bool = False,
    input: str | None = None,
) -> CommandResult:
    with kube_guard():
        return execute("kubectl", *args, capture_stdout=capture_stdout, input=input)


def resource_exists(
    resource: str,
    name: str,
    *,
    namespace: str | None = None,
) -> bool:
    args = [
        "get",
        resource,
        name,
        "--ignore-not-found",
        "--output=name",
    ]
    if namespace is not None:
        args.append(f"--namespace={namespace}")

    result = kubectl(*args, capture_stdout=True)
    return bool(result.stdout.strip())
