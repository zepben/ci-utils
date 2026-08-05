import json
import logging
from collections.abc import Sequence
from contextlib import nullcontext
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from typing import Any

import yaml
from click import ClickException

from zep_dev.k8s import KUBECONF_PATH, kube_guard, kubectl
from zep_dev.k8s_secrets import resolve_registry_credential
from zep_dev.models import (
    LOCAL_REPO_MOUNT_ROOT,
    ClusterComponents,
    LocalRepo,
    OciRepository,
)
from zep_dev.shared import CommandResult, execute

CLUSTER_NAME = "test-cluster"
LOG = logging.getLogger(__name__)


def create_cluster(
    kind_config: Path,
    components: ClusterComponents,
    local_repos: Sequence[Path] = (),
) -> None:
    repos = _load_local_repos(local_repos)
    _create_kind_cluster(kind_config, repos)
    _add_helm_repos(components)
    _install_helm_components(components, repos)


def _load_local_repos(paths: Sequence[Path]) -> tuple[LocalRepo, ...]:
    repos = tuple(LocalRepo(path=path.resolve()) for path in paths)
    seen: set[str] = set()
    for repo in repos:
        if repo.basename in seen:
            raise ClickException(f"duplicate --local-repo basename: {repo.basename}")
        seen.add(repo.basename)
        _validate_repo(repo)
    return repos


def _validate_repo(repo: LocalRepo) -> None:
    try:
        toplevel = Path(
            execute(
                "git",
                "-C",
                str(repo.path),
                "rev-parse",
                "--show-toplevel",
                skip_resolve=True,
                capture_stdout=True,
            ).stdout.strip()
        ).resolve()
    except CalledProcessError as e:
        raise ClickException(f"--local-repo is not a Git work tree: {repo.path}") from e
    if repo.path != toplevel:
        raise ClickException(
            f"--local-repo must be a Git repository toplevel: {repo.path} "
            f"(toplevel is {toplevel})"
        )


def _create_kind_cluster(kind_config: Path, local_repos: Sequence[LocalRepo]) -> None:
    LOG.info("Creating kind cluster")
    existing = kind(
        "get", "clusters", "--quiet", capture_stdout=True
    ).stdout.splitlines()
    if CLUSTER_NAME in existing:
        if local_repos:
            # Ensure that if we have a running cluster, the mounts are the same
            # as passed on the command line. Otherwise we would have a silent
            # and confusing failure mode.
            _validate_existing_worker_mounts(local_repos)
        LOG.info("Reusing existing cluster: %s", CLUSTER_NAME)
        return

    rendered_config = _inject_repo_mounts(kind_config, local_repos)

    config_path = Path("/tmp/kind-config.yaml")
    config_path.write_text(rendered_config, encoding="utf-8")

    kind(
        "create",
        "cluster",
        "--name",
        CLUSTER_NAME,
        "--config",
        str(config_path),
    )
    kind(
        "export",
        "kubeconfig",
        "--name",
        CLUSTER_NAME,
        "--kubeconfig",
        str(KUBECONF_PATH),
    )


def _validate_existing_worker_mounts(local_repos: Sequence[LocalRepo]) -> None:
    """
    Call podman and extract the mounts our running kind cluster has configured.
    If they are not the exact same set as we have passed on the command line --local-repos,
    fail.
    """
    out = kind("get", "nodes", "--name", CLUSTER_NAME, capture_stdout=True)
    workers = tuple(
        name for name in out.stdout.splitlines() if not name.endswith("-control-plane")
    )
    if not workers:
        raise ClickException("--local-repo requires at least one worker node.")

    expected_mounts = {(str(repo.path), repo.container_path) for repo in local_repos}
    for worker in workers:
        existing_mounts = _inspect_live_mounts(worker)
        if existing_mounts != expected_mounts:
            raise ClickException(
                "Existing cluster local-repo mounts do not match --local-repo. "
                "Run: zep-dev cluster teardown"
            )


def _inspect_live_mounts(worker: str) -> set[tuple[str, str]]:
    raw_mounts = podman(
        "inspect",
        worker,
        "--format",
        "{{json .Mounts}}",
        capture_stdout=True,
    ).stdout
    mounts: Any = json.loads(raw_mounts)
    if not isinstance(mounts, list):
        raise ClickException(f"podman inspect returned invalid mounts for {worker}")

    local_mounts = set()
    for mount in mounts:
        if not isinstance(mount, dict):
            continue
        if mount.get("Type") != "bind":
            continue
        source = mount.get("Source")
        destination = mount.get("Destination")
        if not isinstance(source, str) or not isinstance(destination, str):
            continue
        if not destination.startswith(f"{LOCAL_REPO_MOUNT_ROOT}/"):
            continue
        local_mounts.add((str(Path(source).resolve()), destination))

    return local_mounts


def _inject_repo_mounts(kind_config: Path, repos: Sequence[LocalRepo]) -> str:
    config: Any = yaml.safe_load(kind_config.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ClickException(f"kind config must be a mapping: {kind_config}")

    nodes = config.get("nodes", [])
    workers = [node for node in nodes if node.get("role") == "worker"]
    if not workers:
        raise ClickException(
            "--local-repo requires at least one worker node in the kind config"
        )

    # Workers only: control-plane gets no extraMounts. The Argo overlay prevents
    # Argo pods being scheduled on the control-plane nodes.
    for worker in workers:
        mounts = worker.setdefault("extraMounts", [])
        mounts.extend(
            {
                "hostPath": str(repo.path),
                "containerPath": repo.container_path,
                "readOnly": True,
            }
            for repo in repos
        )

    return yaml.safe_dump(config, default_flow_style=False)


def _add_helm_repos(components: ClusterComponents) -> None:
    if components.helm_repos:
        LOG.info("Adding helm repos")
        repo_out = helm("repo", "list", "--no-headers", capture_stdout=True)
        existing_repos = [tuple(s.split()) for s in repo_out.stdout.splitlines()]
        for name, repo in components.helm_repos.items():
            if (name, repo) in existing_repos:
                LOG.info("Not adding %s -> %s as already present", name, repo)
            else:
                helm("repo", "add", name, repo)
        helm("repo", "update")


def _local_repos_overlay(local_repos: Sequence[LocalRepo]) -> dict[str, Any]:
    """Helm values that expose --local-repo mounts to Argo CD.

    kind extraMounts put the repos on workers under LOCAL_REPO_MOUNT_ROOT.
    We hostPath that dir into repo-server, register each as a file:// git
    repo, and set safe.directory=* so git accepts the bind-mounted ownership.
    Affinity keeps repo-server off the control-plane, which has no mounts.
    """
    if not local_repos:
        return {}

    repositories = {
        f"local-{repo.basename}": {
            "name": repo.basename,
            "type": "git",
            "url": f"file://{repo.container_path}",
        }
        for repo in local_repos
    }
    return {
        "configs": {"repositories": repositories},
        "repoServer": {
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "node-role.kubernetes.io/control-plane",
                                        "operator": "DoesNotExist",
                                    }
                                ]
                            }
                        ]
                    }
                }
            },
            "env": [
                {"name": "GIT_CONFIG_COUNT", "value": "1"},
                {"name": "GIT_CONFIG_KEY_0", "value": "safe.directory"},
                {"name": "GIT_CONFIG_VALUE_0", "value": "*"},
            ],
            "volumeMounts": [
                {
                    "name": "local-repos",
                    "mountPath": LOCAL_REPO_MOUNT_ROOT,
                    "readOnly": True,
                }
            ],
            "volumes": [
                {
                    "name": "local-repos",
                    "hostPath": {
                        "path": LOCAL_REPO_MOUNT_ROOT,
                        "type": "Directory",
                    },
                }
            ],
        },
    }


def _install_helm_components(
    components: ClusterComponents,
    local_repos: Sequence[LocalRepo] = (),
) -> None:
    list_out = helm("list", "--all-namespaces", "--deployed", "-q", capture_stdout=True)
    installed = list_out.stdout.splitlines()
    local_repos_overlay = _local_repos_overlay(local_repos)
    LOG.info("Installing cluster components")
    for desired in components.cluster_components:
        if desired.name in installed:
            LOG.info("Skipping already installed chart: %s", desired.name)
        else:
            with TemporaryDirectory() as tmpdir:
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
                if desired.values:
                    values_path = Path(tmpdir) / "values.yaml"
                    values_path.write_text(
                        yaml.safe_dump(desired.values, default_flow_style=False),
                        encoding="utf-8",
                    )
                    install_args.extend(["-f", str(values_path)])
                if desired.local_repo_integration is not None and local_repos_overlay:
                    # TODO: If we add any more of these, don't just add more if conditionals, refactor
                    # how this works. It will get spaghetti real fast otherwise.
                    if desired.local_repo_integration.type != "argo-cd":
                        raise ClickException("Only argo-cd is supported for local_repo_integration.type")
                    overlay_path = Path(tmpdir) / "local-repos-overlay.yaml"
                    overlay_path.write_text(
                        yaml.safe_dump(local_repos_overlay, default_flow_style=False),
                        encoding="utf-8",
                    )
                    install_args.extend(["-f", str(overlay_path)])

                # Install the component.
                helm(*install_args)

        # Apply OCI repo secrets even when Argo is already installed so
        # credentials stay current across repeated cluster create runs.
        if desired.local_repo_integration is not None:
            _apply_argo_oci_repository_secrets(
                desired.namespace,
                desired.local_repo_integration.oci_repositories,
            )


def _apply_argo_oci_repository_secrets(
    namespace: str,
    repositories: Sequence[OciRepository],
) -> None:
    """Apply Argo CD repository Secrets for Helm OCI registries.

    Argo CD discovers private Helm OCI repos from Secrets labeled
    argocd.argoproj.io/secret-type=repository; see
    https://argo-cd.readthedocs.io/en/stable/operator-manual/secret-argocd-repo-credentials/
    """
    for repository in repositories:
        username, password = resolve_registry_credential(repository.registry)
        manifest = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {
                "name": repository.name,
                "namespace": namespace,
                "labels": {"argocd.argoproj.io/secret-type": "repository"},
            },
            "stringData": {
                "type": "helm",
                "name": repository.name,
                "enableOCI": "true",
                "url": repository.url,
                "username": username,
                "password": password,
            },
        }
        LOG.info("Applying Argo OCI repository secret: %s", repository.url)
        kubectl(
            "apply",
            "-f",
            "-",
            input=yaml.safe_dump(manifest, default_flow_style=False),
        )


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


def kind(*args: str, capture_stdout: bool = False) -> CommandResult:
    return execute("kind", *args, capture_stdout=capture_stdout)


def podman(*args: str, capture_stdout: bool = False) -> CommandResult:
    return execute(
        "podman",
        *args,
        capture_stdout=capture_stdout,
        skip_resolve=True,
    )


def helm(*args: str, capture_stdout: bool = False) -> CommandResult:
    with kube_guard():
        return execute("helm", *args, capture_stdout=capture_stdout)
