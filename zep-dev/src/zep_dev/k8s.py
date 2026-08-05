import os
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from zep_dev.shared import CommandResult, execute

KUBECONF_PATH = Path("/tmp/kind-k8s-conf.yaml")


@contextmanager
def kube_guard() -> Generator[None]:
    """
    Ensure when we run commands, we are using our kind KUBECONFIG.
    This is to prevent accidentally targeting production clusters.
    """
    og_conf = os.environ.get("KUBECONFIG")
    os.environ["KUBECONFIG"] = str(KUBECONF_PATH)
    yield
    if og_conf is not None:
        os.environ["KUBECONFIG"] = og_conf
    else:
        os.environ.pop("KUBECONFIG", None)


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
