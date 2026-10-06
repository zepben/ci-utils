import json
import logging
from base64 import b64decode
from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from copy import deepcopy
from importlib.resources import as_file, files
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, assert_never

import yaml
from click import ClickException

from zep_dev.cnpg import apply_cnpg_component as apply_cnpg_component
from zep_dev.cnpg import cnpg_manifests as cnpg_manifests
from zep_dev.k8s import KUBECONF_PATH, kube_guard, kubectl, resource_exists
from zep_dev.k8s_secrets import resolve_registry_credential
from zep_dev.models import (
    LOCAL_REPO_MOUNT_ROOT,
    ClusterComponent,
    ClusterComponentItem,
    ClusterComponents,
    CnpgComponent,
    HostMount,
    LoadDbCredentials,
    LocalRepo,
    OciRepository,
    RawManifestComponent,
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
    image_archive: Path | None = None,
) -> None:
    repos = load_local_repos(local_repos)
    create_kind_cluster(kind_config, repos)
    if image_archive is not None:
        if image_archive.exists():
            load_image_archive(image_archive)
        else:
            LOG.info(
                "Image archive not found; continuing without it: %s",
                image_archive,
            )
    apply_builtin_storage_classes()
    add_helm_repos(components.helm_repos)
    install_helm_components(
        components.cluster_components, repos, source_dir=components.source_dir
    )


def load_image_archive(
    archive: Path,
    *,
    cluster_name: str = CLUSTER_NAME,
) -> None:
    if not archive.is_file() or archive.stat().st_size == 0:
        raise ClickException(f"image archive is missing or empty: {archive}")
    kind("load", "image-archive", str(archive), "--name", cluster_name)


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
    if repo.path != toplevel:
        raise ClickException(
            f"--local-repo must be a Git repository toplevel: {repo.path} "
            f"(toplevel is {toplevel})"
        )


def create_kind_cluster(
    kind_config: Path | dict[str, Any],
    local_repos: Sequence[LocalRepo] = (),
    *,
    host_mounts: Sequence[HostMount] = (),
    cluster_name: str = CLUSTER_NAME,
) -> None:
    LOG.info("Creating kind cluster")
    mounts = tuple(repo.to_host_mount() for repo in local_repos) + tuple(host_mounts)
    existing = kind(
        "get", "clusters", "--quiet", capture_stdout=True
    ).stdout.splitlines()
    if cluster_name in existing:
        if mounts:
            validate_existing_worker_mounts(mounts, cluster_name=cluster_name)
        LOG.info("Reusing existing cluster: %s", cluster_name)
    else:
        rendered_config = inject_host_mounts(kind_config, mounts)

        config_path = Path("/tmp/kind-config.yaml")
        config_path.write_text(rendered_config, encoding="utf-8")

        kind(
            "create",
            "cluster",
            "--name",
            cluster_name,
            "--config",
            str(config_path),
        )

    # Always export kubeconfig again.
    # Reuse needs a fresh file if /tmp was cleared.
    kind(
        "export",
        "kubeconfig",
        "--name",
        cluster_name,
        "--kubeconfig",
        str(KUBECONF_PATH),
    )


def validate_existing_worker_mounts(
    host_mounts: Sequence[HostMount],
    *,
    cluster_name: str = CLUSTER_NAME,
) -> None:
    """Fail if the live worker bind mounts are not the mounts you requested.

    A mismatch fails later with no clear error.
    """
    out = kind("get", "nodes", "--name", cluster_name, capture_stdout=True)
    workers = tuple(
        name for name in out.stdout.splitlines() if not name.endswith("-control-plane")
    )
    if not workers:
        raise RuntimeError("host mounts require at least one worker node.")

    expected = {
        (str(mount.host_path.resolve()), mount.node_path) for mount in host_mounts
    }
    expected_dests = {dest for _, dest in expected}
    for worker in workers:
        existing_mounts = {
            pair for pair in inspect_bind_mounts(worker) if pair[1] in expected_dests
        }
        if existing_mounts != expected:
            raise RuntimeError(
                "Existing cluster host mounts do not match the Profile / --local-repo. "
                "Run: zep-dev deployment destroy --profile <path> "
                "(or zep-dev cluster teardown for chart-test clusters)"
            )


def inspect_bind_mounts(worker: str) -> set[tuple[str, str]]:
    raw_mounts = podman(
        "inspect",
        worker,
        "--format",
        "{{json .Mounts}}",
        capture_stdout=True,
    ).stdout
    mounts: Any = json.loads(raw_mounts)
    if not isinstance(mounts, list):
        raise RuntimeError(f"podman inspect returned invalid mounts for {worker}")

    bind_mounts: set[tuple[str, str]] = set()
    for mount in mounts:
        if not isinstance(mount, dict):
            continue
        if mount.get("Type") != "bind":
            continue
        source = mount.get("Source")
        destination = mount.get("Destination")
        if not isinstance(source, str) or not isinstance(destination, str):
            continue
        bind_mounts.add((str(Path(source).resolve()), destination))

    return bind_mounts


def inject_host_mounts(
    kind_config: Path | dict[str, Any], host_mounts: Sequence[HostMount]
) -> str:
    config: Any = (
        yaml.safe_load(kind_config.read_text(encoding="utf-8"))
        if isinstance(kind_config, Path)
        else deepcopy(kind_config)
    )
    if not isinstance(config, dict):
        raise ValueError(f"kind config must be a mapping: {kind_config}")

    nodes = config.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("kind config nodes must be a list")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError(f"kind config nodes[{index}] must be a mapping")
        if node.get("role") == "worker" and "extraMounts" in node:
            if not isinstance(node["extraMounts"], list):
                raise ValueError(
                    f"kind config nodes[{index}].extraMounts must be a list"
                )
    workers = [node for node in nodes if node.get("role") == "worker"]
    if host_mounts and not workers:
        raise ValueError(
            "host mounts require at least one worker node in the kind config"
        )

    # Put extraMounts on workers only.
    # The control-plane node has none.
    for worker in workers:
        mounts = worker.setdefault("extraMounts", [])
        mounts.extend(
            {
                "hostPath": str(mount.host_path),
                "containerPath": mount.node_path,
                "readOnly": mount.read_only,
            }
            for mount in host_mounts
        )

    return yaml.safe_dump(config, default_flow_style=False)


def add_helm_repos(repositories: Mapping[str, str]) -> None:
    if repositories:
        LOG.info("Adding helm repos")
        repo_out = helm("repo", "list", "--no-headers", capture_stdout=True)
        existing_repos = [tuple(s.split()) for s in repo_out.stdout.splitlines()]
        for name, repo in repositories.items():
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
    components: Sequence[ClusterComponentItem],
    local_repos: Sequence[LocalRepo] = (),
    *,
    source_dir: Path | None = None,
) -> None:
    list_out = helm("list", "--all-namespaces", "--deployed", "-q", capture_stdout=True)
    installed = list_out.stdout.splitlines()
    repos_overlay = local_repos_overlay(local_repos)
    LOG.info("Installing cluster components")
    for desired in components:
        match desired:
            case RawManifestComponent():
                for url in desired.raw_manifests:
                    kubectl("apply", "--server-side", "-f", url)
                kubectl(
                    "wait",
                    "--for=condition=Established",
                    "customresourcedefinitions",
                    "--all",
                    f"--timeout={desired.wait_timeout}",
                )
            case CnpgComponent():
                apply_cnpg_component(desired)
            case ClusterComponent():
                reconcile_helm_component(
                    desired,
                    source_dir=source_dir,
                    installed=installed,
                    local_repos_overlay=repos_overlay,
                )
            case _:
                assert_never(desired)


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


def teardown_cluster(*, cluster_name: str = CLUSTER_NAME) -> None:
    LOG.info("Tearing down cluster")
    kind("delete", "cluster", "--name", cluster_name)


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


def helm(
    *args: str,
    capture_stdout: bool = False,
    capture_stderr: bool = False,
    check: bool = True,
    timeout: float | None = None,
) -> CommandResult:
    with kube_guard():
        if timeout is not None:
            return execute(
                "helm",
                *args,
                capture_stdout=capture_stdout,
                capture_stderr=capture_stderr,
                check=check,
                timeout=timeout,
            )
        return execute(
            "helm",
            *args,
            capture_stdout=capture_stdout,
            capture_stderr=capture_stderr,
            check=check,
        )
