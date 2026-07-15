import logging
import os
from collections.abc import Generator
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory

from local_k8s.models import ClusterComponents
from local_k8s.shared import execute

CLUSTER_NAME = "test-cluster"

# Write this to a file in /tmp to avoid clashes with whatever the
# user may have configured. Also is a safety issue, don't want to
# accidentlly target production clusters
KUBECONF_PATH = Path("/tmp/kind-k8s-conf.yaml")
LOG = logging.getLogger(__name__)


@contextmanager
def kube_guard() -> Generator[None]:
    """
    Ensure when we run commands, we are using our kind KUBECONFIG.
    This is to prevent accidentally a production cluster.
    """
    og_conf = os.environ.get("KUBECONFIG")
    os.environ["KUBECONFIG"] = str(KUBECONF_PATH)
    yield
    if og_conf is not None:
        os.environ["KUBECONFIG"] = og_conf
    else:
        os.environ.pop("KUBECONFIG", None)


def create_cluster(kind_config: Path, components: ClusterComponents) -> None:
    _create_kind_cluster(kind_config)
    _add_helm_repos(components)
    _install_helm_components(components)


def _create_kind_cluster(kind_config: Path) -> None:
    LOG.info("Creating kind cluster")
    for line in kind("get", "clusters", "--quiet").splitlines():
        if line == CLUSTER_NAME:
            LOG.info("Reusing existing cluster: %s", CLUSTER_NAME)
            break
    else:
        kind(
            "create",
            "cluster",
            "--name",
            CLUSTER_NAME,
            "--config",
            str(kind_config),
        )
    kind(
        "export",
        "kubeconfig",
        "--name",
        CLUSTER_NAME,
        "--kubeconfig",
        str(KUBECONF_PATH),
    )


def _add_helm_repos(components: ClusterComponents) -> None:
    if components.helm_repos:
        LOG.info("Adding helm repos")
        repo_out = helm("repo", "list", "--no-headers")
        existing_repos = [tuple(s.split()) for s in repo_out.splitlines()]
        for name, repo in components.helm_repos.items():
            if (name, repo) in existing_repos:
                LOG.info("Not adding %s -> %s as already present", name, repo)
            else:
                helm("repo", "add", name, repo)
        helm("repo", "update")


def _install_helm_components(components: ClusterComponents) -> None:
    list_out = helm("list", "--all-namespaces", "--deployed", "-q")
    installed = list_out.splitlines()
    LOG.info("Installing cluster components")
    for desired in components.cluster_components:
        if desired.name in installed:
            LOG.info("Skipping already installed chart: %s", desired.name)
        else:
            install_args: list[str] = [
                "install",
                desired.name,
                desired.chart,
                "--namespace",
                desired.namespace,
                "--create-namespace",
                "--version",
                desired.version,
                "--wait",
            ]
            for key, value in desired.set.items():
                install_args.extend(["--set", f"{key}={value}"])
            helm(*install_args)


def teardown_cluster() -> None:
    LOG.info("Tearing down cluster")
    kind("delete", "cluster", "--name", CLUSTER_NAME)


def take_debug_dump(filter_namespaces: list[str], out_dir: Path | None) -> None:
    dir_decorator = (
        TemporaryDirectory(prefix="/var/tmp/debug-dump-")
        if out_dir is None
        else nullcontext(
            enter_result=out_dir,
        )
    )
    with dir_decorator as tmpdir:
        tmpdir = Path(tmpdir)
        kubectl(
            "cluster-info",
            "dump",
            "--all-namespaces",
            "-o",
            "yaml",
            "--output-directory",
            str(tmpdir),
        )
        dump_to_stdout(filter_namespaces, tmpdir)


def dump_to_stdout(filter_namespaces: list[str], out_dir: Path) -> None:
    for namespace in out_dir.iterdir():
        if not namespace.is_dir():
            continue
        if not filter_namespaces or namespace.name in filter_namespaces:
            for manifest in namespace.glob("*.yaml"):
                print(manifest.read_text())
            for path in namespace.iterdir():
                if path.is_dir():
                    for log_file in path.glob("*.txt"):
                        print(log_file.read_text())


def kind(*args: str) -> str:
    return execute("kind", *args)


def helm(*args: str) -> str:
    with kube_guard():
        return execute("helm", *args)


def kubectl(*args: str) -> str:
    with kube_guard():
        return execute("kubectl", *args)
