"""Bring up a multi-app Kind environment from a Profile."""

from __future__ import annotations

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal, NamedTuple

import yaml
from click import echo

from zep_dev import cluster
from zep_dev.bindings import load_bindings
from zep_dev.commands.terraform.commands import (
    apply_terraform,
    destroy_terraform,
    terraform_state_path,
)
from zep_dev.distribution import (
    APP_HELM_TIMEOUT,
    CHART_OCI_PREFIX,
    GHCR_REGISTRY,
    ComponentName,
    Components,
    Profile,
    PullRequestLocator,
    VersionLocator,
)
from zep_dev.git_cache import GitCache
from zep_dev.github_api import GitHubAPI
from zep_dev.k8s import kubectl, resource_exists
from zep_dev.k8s_secrets import create_image_pull_secret, resolve_registry_credential
from zep_dev.models import ClusterComponent, HostMount, LocalManifestComponent
from zep_dev.oci import check_oci_chart, probe_oci_chart
from zep_dev.source_chart import resolve_source_chart
from zep_dev.terraform_roots import (
    generate_profile_terraform_roots,
    preflight_terraform,
    profile_tf_dir,
    read_profile_tf_meta,
)


class InstallRef(NamedTuple):
    name: ComponentName
    chart: str
    version: str
    source: Literal["version", "pullRequest", "commit"]


def format_install_refs(refs: Sequence[InstallRef]) -> str:
    return ", ".join(f"{ref.name}:{ref.version}" for ref in refs)


def install_refs(components: Components) -> list[InstallRef]:
    """Resolve Distribution locators to OCI chart references."""
    git_cache: GitCache | None = None
    api: GitHubAPI | None = None
    refs: list[InstallRef] = []
    for name, locator in components.iter_locators():
        chart = f"{CHART_OCI_PREFIX}/{name}"
        if isinstance(locator, VersionLocator):
            refs.append(InstallRef(name, chart, locator.version, "version"))
            continue
        if git_cache is None or api is None:
            git_cache = GitCache()
            api = GitHubAPI()
        _, _, version = resolve_source_chart(name, locator, git_cache, api)
        source: Literal["pullRequest", "commit"] = (
            "pullRequest" if isinstance(locator, PullRequestLocator) else "commit"
        )
        refs.append(InstallRef(name, chart, version, source))
    return refs


def resolve_path(source_dir: Path, relative_or_absolute: str) -> Path:
    path = Path(relative_or_absolute)
    if not path.is_absolute():
        path = source_dir / path
    return path.resolve()


def check_local_paths(profile: Profile) -> None:
    """Validate Profile-local helper charts and manifests."""
    source_dir = profile.source_dir
    if source_dir is None:
        raise ValueError("Profile has no source_dir; load via Profile.from_path")

    for component in profile.cluster_components:
        if isinstance(component, ClusterComponent):
            check_local_chart(component.chart, source_dir)
            for config_map in component.config_maps_from_file:
                for filename, relative in config_map.from_file.items():
                    path = resolve_path(source_dir, relative)
                    if not path.is_file():
                        raise FileNotFoundError(
                            f"config_maps_from_file {component.name}/{filename} "
                            f"not found: {path}"
                        )
        elif isinstance(component, LocalManifestComponent):
            for relative in component.manifests:
                path = resolve_path(source_dir, relative)
                if not path.is_file():
                    raise FileNotFoundError(
                        f"local manifest {component.name}/{relative} not found: {path}"
                    )


def check_local_chart(chart: str, source_dir: Path) -> None:
    if not chart.startswith(".") and not Path(chart).is_absolute():
        return
    resolved = resolve_path(source_dir, chart)
    if not resolved.exists():
        raise FileNotFoundError(f"local chart not found: {resolved}")


def check_install_artifacts(refs: Sequence[InstallRef]) -> None:
    for ref in refs:
        if ref.source == "version":
            check_oci_chart(ref.name, ref.version)
            continue
        if not probe_oci_chart(ref.name, ref.version):
            raise FileNotFoundError(
                f"Missing OCI chart for components.{ref.name}.{ref.source} "
                f"({ref.version}); run distribution build first"
            )


def check_profile_secrets(profile: Profile) -> None:
    """Fail if any Profile-declared secret env var is missing or empty."""
    for secret in profile.secrets:
        secret.resolve_value()


class PreflightResult(NamedTuple):
    refs: list[InstallRef]
    host_mounts: list[HostMount]
    deployments_root: Path | None


def preflight(profile: Profile) -> PreflightResult:
    refs = install_refs(profile.distribution.components)
    echo(
        f"Preflight: validating profile and chart artifacts ({format_install_refs(refs)})"
    )
    host_mounts: list[HostMount] = []
    deployments_root: Path | None = None
    if profile.requires_bindings():
        bindings = load_bindings()
        host_mounts = profile.resolved_host_mounts(bindings)
        if profile.terraform is not None:
            deployments_root = preflight_terraform(
                deployments_root=bindings.require_deployments_root(),
                contracts=list(profile.terraform.contracts),
            )
    check_local_paths(profile)
    check_profile_secrets(profile)
    check_install_artifacts(refs)
    resolve_registry_credential(GHCR_REGISTRY)
    echo("Preflight OK")
    return PreflightResult(refs, host_mounts, deployments_root)


def ensure_kind_cluster(
    profile: Profile,
    *,
    allow_reuse: bool,
    host_mounts: Sequence[HostMount] = (),
) -> None:
    cluster_name = profile.metadata.name
    existing = cluster.kind(
        "get", "clusters", "--quiet", capture_stdout=True
    ).stdout.splitlines()
    if cluster_name in existing and not allow_reuse:
        raise RuntimeError(
            f"Kind cluster {cluster_name!r} already exists. "
            f"Run: zep-dev platform destroy --profile <path> "
            f"or re-run with --allow-reuse"
        )

    if cluster_name in existing:
        echo(f"Reusing Kind cluster {cluster_name!r} (--allow-reuse)")
    else:
        echo(f"Creating Kind cluster {cluster_name!r}")

    cluster.create_kind_cluster(
        profile.kind.config,
        host_mounts=host_mounts,
        cluster_name=cluster_name,
    )


def install_distribution_apps(
    profile: Profile,
    refs: Sequence[InstallRef] | None = None,
) -> None:
    if refs is None:
        refs = install_refs(profile.distribution.components)
    echo(
        f"Installing {len(refs)} apps in parallel ({format_install_refs(refs)}); "
        f"waiting up to {APP_HELM_TIMEOUT} each"
    )
    with TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        def install(ref: InstallRef) -> None:
            echo(f"  started {ref.name}:{ref.version}")
            helm_upgrade_install_app(profile, ref, tmp)

        with ThreadPoolExecutor(max_workers=len(refs) or 1) as pool:
            futures = {pool.submit(install, ref): ref for ref in refs}
            failures: list[str] = []
            for future in as_completed(futures):
                ref = futures[future]
                error = future.exception()
                if error is not None:
                    echo(f"  failed {ref.name}:{ref.version}")
                    failures.append(f"{ref.name}: {error}")
                else:
                    echo(f"  ready {ref.name}:{ref.version}")
        if failures:
            raise RuntimeError("App install failed:\n" + "\n".join(failures))


def helm_upgrade_install_app(profile: Profile, ref: InstallRef, tmp: Path) -> None:
    args = [
        "upgrade",
        "--install",
        ref.name,
        ref.chart,
        "--version",
        ref.version,
        "--namespace",
        profile.namespace,
        "--wait",
        f"--timeout={APP_HELM_TIMEOUT}",
    ]
    app = profile.apps.get(ref.name)
    if app is not None and app.values:
        values_path = tmp / f"{ref.name}-values.yaml"
        values_path.write_text(
            yaml.safe_dump(app.values, default_flow_style=False),
            encoding="utf-8",
        )
        args.extend(["-f", str(values_path)])
    cluster.helm(*args)


def apply_profile_terraform(profile: Profile, deployments_root: Path) -> None:
    if profile.terraform is None:
        return
    roots = generate_profile_terraform_roots(
        profile_name=profile.metadata.name,
        namespace=profile.namespace,
        deployments_root=deployments_root,
        contracts=list(profile.terraform.contracts),
    )
    echo(f"Applying {len(roots)} Terraform runtime contract(s)")
    for tf_root in roots:
        echo(f"  terraform apply {tf_root}")
        apply_terraform(tf_root, profile.namespace)


def destroy_profile_terraform(profile_name: str) -> None:
    """Destroy generated TF roots for a Profile when state exists."""
    meta = read_profile_tf_meta(profile_name)
    if meta is None:
        return
    base = profile_tf_dir(profile_name)
    for contract in meta.contracts:
        root = base / contract
        if not root.is_dir():
            continue
        state = terraform_state_path(root.resolve(), meta.namespace)
        if not state.is_file():
            echo(f"  skip terraform destroy {contract} (no state)")
            continue
        echo(f"  terraform destroy {root}")
        destroy_terraform(root, meta.namespace)


def apply_profile(
    profile: Profile,
    *,
    allow_reuse: bool = False,
    image_archive: Path | None = None,
) -> None:
    result = preflight(profile)
    ensure_kind_cluster(
        profile, allow_reuse=allow_reuse, host_mounts=result.host_mounts
    )
    if image_archive is not None:
        echo(f"Loading image archive into {profile.metadata.name!r}: {image_archive}")
        cluster.load_image_archive(image_archive, cluster_name=profile.metadata.name)

    # kubectl apply does not create namespaces; Helm --create-namespace only
    # covers chart installs. Data-plane manifests need the Profile namespace first.
    echo(f"Ensuring namespace {profile.namespace!r}")
    if not resource_exists("namespace", profile.namespace):
        kubectl("create", "namespace", profile.namespace)

    echo("Installing cluster helpers")
    cluster.apply_builtin_storage_classes()
    helpers = profile.to_cluster_components()
    cluster.add_helm_repos(helpers)
    cluster.install_helm_components(helpers)

    echo(f"Ensuring image-pull secret in {profile.namespace!r}")
    create_image_pull_secret(profile.namespace)
    apply_profile_secrets(profile)

    if result.deployments_root is not None:
        apply_profile_terraform(profile, result.deployments_root)
    install_distribution_apps(profile, result.refs)


def apply_profile_secrets(profile: Profile) -> None:
    """Create Secrets declared on the Profile.

    Each ``CiSecret`` names a Secret and an env var whose value is an env-file
    body for ``kubectl --from-env-file``.
    """
    for secret in profile.secrets:
        if resource_exists("secret", secret.name, namespace=profile.namespace):
            continue
        echo(f"Creating secret {secret.name!r} in {profile.namespace!r}")
        kubectl(
            f"--namespace={profile.namespace}",
            "create",
            "secret",
            "generic",
            secret.name,
            "--from-env-file=/dev/stdin",
            input=secret.resolve_value(),
        )
