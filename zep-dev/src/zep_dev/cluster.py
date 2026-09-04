import json
import logging
from base64 import b64decode
from collections.abc import Sequence
from contextlib import nullcontext
from importlib.resources import as_file, files
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from typing import Any

import yaml
from click import ClickException

from zep_dev.k8s import KUBECONF_PATH, kube_guard, kubectl, resource_exists
from zep_dev.k8s_secrets import resolve_registry_credential
from zep_dev.models import (
    LOCAL_REPO_MOUNT_ROOT,
    ClusterComponent,
    ClusterComponents,
    LoadDbCredentials,
    LocalRepo,
    OciRepository,
)
from zep_dev.shared import CommandResult, execute

CLUSTER_NAME = "test-cluster"
LOG = logging.getLogger(__name__)

# We package these to simulate the same storage classes that
# exist on the cloud provider k8s clusters. This just eases
# testing as we don't need to handle the case that these don't
# exist everywhere we expect them to.
BUILTIN_STORAGE_CLASS_RESOURCES = (
    "storageclass-ebs-sc.yaml",
    "storageclass-managed-csi.yaml",
)


def create_cluster(
    kind_config: Path,
    components: ClusterComponents,
    local_repos: Sequence[Path] = (),
) -> None:
    repos = load_local_repos(local_repos)
    create_kind_cluster(kind_config, repos)
    apply_builtin_storage_classes()
    add_helm_repos(components)
    install_helm_components(components, repos)


def load_local_repos(paths: Sequence[Path]) -> tuple[LocalRepo, ...]:
    repos = tuple(LocalRepo(path=path.resolve()) for path in paths)
    seen: set[str] = set()
    for repo in repos:
        if repo.basename in seen:
            raise ClickException(f"duplicate --local-repo basename: {repo.basename}")
        seen.add(repo.basename)
        validate_repo(repo)
    return repos


def validate_repo(repo: LocalRepo) -> None:
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


def create_kind_cluster(kind_config: Path, local_repos: Sequence[LocalRepo]) -> None:
    LOG.info("Creating kind cluster")
    existing = kind(
        "get", "clusters", "--quiet", capture_stdout=True
    ).stdout.splitlines()
    if CLUSTER_NAME in existing:
        if local_repos:
            # Ensure that if we have a running cluster, the mounts are the same
            # as passed on the command line. Otherwise we would have a silent
            # and confusing failure mode.
            validate_existing_worker_mounts(local_repos)
        LOG.info("Reusing existing cluster: %s", CLUSTER_NAME)
        return

    rendered_config = inject_repo_mounts(kind_config, local_repos)

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


def validate_existing_worker_mounts(local_repos: Sequence[LocalRepo]) -> None:
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
        existing_mounts = inspect_live_mounts(worker)
        if existing_mounts != expected_mounts:
            raise ClickException(
                "Existing cluster local-repo mounts do not match --local-repo. "
                "Run: zep-dev cluster teardown"
            )


def inspect_live_mounts(worker: str) -> set[tuple[str, str]]:
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


def inject_repo_mounts(kind_config: Path, repos: Sequence[LocalRepo]) -> str:
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


def add_helm_repos(components: ClusterComponents) -> None:
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


def apply_builtin_storage_classes() -> None:
    """Apply Kind-local StorageClasses named the same as the AWS/Azure ones."""
    resources = files("zep_dev.resources")
    for name in BUILTIN_STORAGE_CLASS_RESOURCES:
        with as_file(resources.joinpath(name)) as path:
            kubectl("apply", "-f", str(path))


def local_repos_overlay(local_repos: Sequence[LocalRepo]) -> dict[str, Any]:
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


def install_helm_components(
    components: ClusterComponents,
    local_repos: Sequence[LocalRepo] = (),
) -> None:
    list_out = helm("list", "--all-namespaces", "--deployed", "-q", capture_stdout=True)
    installed = list_out.stdout.splitlines()
    repos_overlay = local_repos_overlay(local_repos)
    LOG.info("Installing cluster components")
    for desired in components.cluster_components:
        reconcile_helm_component(
            desired,
            source_dir=components.source_dir,
            installed=installed,
            local_repos_overlay=repos_overlay,
        )


def reconcile_helm_component(
    desired: ClusterComponent,
    *,
    source_dir: Path | None,
    installed: Sequence[str],
    local_repos_overlay: dict[str, Any],
) -> None:
    if desired.config_maps_from_file:
        apply_configmaps_from_file(desired, source_dir)

    if desired.name in installed:
        LOG.info("Skipping already installed chart: %s", desired.name)
    else:
        value_layers = helm_value_layers(desired, local_repos_overlay)
        install_helm_component(desired, value_layers, source_dir)

    wait_for_resources(desired)
    if desired.load_db_credentials is not None:
        apply_load_db_credentials(desired, desired.load_db_credentials)

    if desired.local_repo_integration:
        apply_argo_oci_repository_secrets(
            desired.namespace,
            desired.local_repo_integration.oci_repositories,
        )


def wait_for_resources(desired: ClusterComponent) -> None:
    for wait_for in desired.wait_for:
        namespace = wait_for.namespace or desired.namespace
        kubectl(
            "wait",
            f"--for={wait_for.for_}",
            wait_for.resource,
            f"--namespace={namespace}",
            f"--timeout={wait_for.timeout}",
        )


def apply_load_db_credentials(
    desired: ClusterComponent,
    credentials: LoadDbCredentials,
) -> None:
    source = kubectl(
        "get",
        "secret",
        credentials.from_secret,
        f"--namespace={desired.namespace}",
        "--output=json",
        capture_stdout=True,
    )
    source_data: dict[str, str] = json.loads(source.stdout).get("data", {})
    config = {
        "host": secret_data(source_data, "host"),
        "port": int(secret_data(source_data, "port")),
        "name": credentials.database,
        "username": secret_data(source_data, "username", "user"),
        "password": secret_data(source_data, "password"),
    }
    manifest = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": "ewb-load-database-config",
            "namespace": desired.namespace,
        },
        "type": "Opaque",
        "stringData": {"load-database.json": json.dumps(config, separators=(",", ":"))},
    }
    kubectl(
        "apply",
        "-f",
        "-",
        input=yaml.safe_dump(manifest, default_flow_style=False),
    )


def secret_data(source_data: dict[str, str], *keys: str) -> str:
    for key in keys:
        encoded = source_data.get(key)
        if encoded is not None:
            return b64decode(encoded, validate=True).decode("utf-8")
    raise ClickException(f"Secret data does not contain any of: {', '.join(keys)}")


def apply_configmaps_from_file(
    desired: ClusterComponent,
    source_dir: Path | None,
) -> None:
    if not resource_exists("namespace", desired.namespace):
        kubectl("create", "namespace", desired.namespace)
    for config_map in desired.config_maps_from_file:
        kubectl(
            "apply",
            "-f",
            "-",
            input=yaml.safe_dump(
                config_map.manifest(desired.namespace, source_dir),
                default_flow_style=False,
            ),
        )


def helm_value_layers(
    desired: ClusterComponent,
    local_repos_overlay: dict[str, Any],
) -> list[tuple[str, dict[str, Any]]]:
    value_layers = []
    if desired.values:
        value_layers.append(("values.yaml", desired.values))
    if desired.local_repo_integration is not None and local_repos_overlay:
        value_layers.append(("local-repos-overlay.yaml", local_repos_overlay))
    return value_layers


def install_helm_component(
    desired: ClusterComponent,
    value_layers: Sequence[tuple[str, dict[str, Any]]],
    source_dir: Path | None,
) -> None:
    chart = resolve_chart_path(desired.chart, source_dir)
    with TemporaryDirectory() as tmpdir:
        install_args: list[str] = [
            "install",
            desired.name,
            chart,
            "--namespace",
            desired.namespace,
            "--create-namespace",
            "--version",
            desired.version,
            "--wait",
        ]
        for filename, values in value_layers:
            values_path = Path(tmpdir) / filename
            values_path.write_text(
                yaml.safe_dump(values, default_flow_style=False),
                encoding="utf-8",
            )
            install_args.extend(["-f", str(values_path)])

        helm(*install_args)


def resolve_chart_path(chart: str, source_dir: Path | None) -> str:
    chart_path = Path(chart)
    if not chart.startswith(".") and not chart_path.is_absolute():
        return chart
    if source_dir is None:
        raise ClickException("local chart requires a components file path")
    return str((source_dir / chart_path).resolve())


def apply_argo_oci_repository_secrets(
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
