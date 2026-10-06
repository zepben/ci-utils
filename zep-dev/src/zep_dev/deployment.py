import logging
import os
import signal
import subprocess
from collections.abc import Sequence
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from typing import NamedTuple

import yaml
from click import echo

from zep_dev import cluster
from zep_dev.bindings import load_bindings
from zep_dev.chart_artifacts import ChartRef, ChartResolver, format_chart_refs
from zep_dev.commands.terraform.commands import apply_terraform
from zep_dev.distribution import APP_HELM_TIMEOUT, GHCR_REGISTRY
from zep_dev.k8s import kube_guard, kubectl, resource_exists
from zep_dev.k8s_secrets import create_image_pull_secret, resolve_registry_credential
from zep_dev.models import ClusterComponent, HostMount
from zep_dev.profile import Profile
from zep_dev.shared import resolve
from zep_dev.terraform_roots import (
    generate_profile_terraform_root,
    preflight_terraform,
    profile_tf_dir,
)

LOG = logging.getLogger(__name__)
_HELM_TERMINATION_GRACE_SECONDS = 2.0


class PreflightResult(NamedTuple):
    refs: list[ChartRef]
    host_mounts: list[HostMount]
    deployments_root: Path | None


def require_source_dir(profile: Profile) -> Path:
    if profile.source_dir is None:
        raise ValueError("Profile has no source_dir; load via Profile.from_path")
    return profile.source_dir


def resolve_path(source_dir: Path, relative_or_absolute: str) -> Path:
    path = Path(relative_or_absolute)
    if not path.is_absolute():
        path = source_dir / path
    return path.resolve()


def check_local_paths(profile: Profile) -> None:
    source_dir = require_source_dir(profile)

    for component in profile.k8s.components:
        if not isinstance(component, ClusterComponent):
            continue
        chart = component.chart
        if chart.startswith(".") or Path(chart).is_absolute():
            resolved = resolve_path(source_dir, chart)
            if not resolved.exists():
                raise FileNotFoundError(f"local chart not found: {resolved}")
        for config_map in component.config_maps_from_file:
            for filename, relative in config_map.from_file.items():
                path = resolve_path(source_dir, relative)
                if not path.is_file():
                    raise FileNotFoundError(
                        f"config_maps_from_file {component.name}/{filename} "
                        f"not found: {path}"
                    )

    for manifest in profile.runtime.manifests:
        for relative in manifest.files:
            path = resolve_path(source_dir, relative)
            if not path.is_file():
                raise FileNotFoundError(
                    f"runtime.manifests file {relative!r} not found: {path}"
                )


def preflight(profile: Profile) -> PreflightResult:
    resolver = ChartResolver()
    refs = resolver.resolve_all(profile.distribution.charts)
    echo(
        f"Preflight: validating profile and chart artifacts ({format_chart_refs(refs)})"
    )
    host_mounts: list[HostMount] = []
    deployments_root: Path | None = None
    if profile.requires_bindings():
        bindings = load_bindings()
        host_mounts = profile.resolved_host_mounts(bindings)
        if profile.runtime.databases:
            deployments_root = preflight_terraform(
                deployments_root=bindings.require_deployments_root(),
                databases=list(profile.runtime.databases),
            )
    check_local_paths(profile)
    for secret in profile.secrets:
        secret.resolve_value()
    resolver.check_all(refs)
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
            f"Run: zep-dev deployment destroy --profile <path> "
            f"or re-run with --allow-reuse"
        )

    if cluster_name in existing:
        echo(f"Reusing Kind cluster {cluster_name!r} (--allow-reuse)")
    else:
        echo(f"Creating Kind cluster {cluster_name!r}")

    cluster.create_kind_cluster(
        profile.k8s.kind.config,
        host_mounts=host_mounts,
        cluster_name=cluster_name,
    )


def install_distribution_apps(
    profile: Profile,
    refs: Sequence[ChartRef] | None = None,
) -> None:
    if refs is None:
        refs = ChartResolver().resolve_all(profile.distribution.charts)
    echo(
        f"Installing {len(refs)} apps in parallel ({format_chart_refs(refs)}); "
        f"waiting up to {APP_HELM_TIMEOUT} each"
    )
    if not refs:
        return
    resolve("helm")
    with TemporaryDirectory() as tmpdir, kube_guard():
        tmp = Path(tmpdir)
        processes: dict[subprocess.Popen[str], ChartRef] = {}
        try:
            for ref in refs:
                args = helm_install_args(profile, ref, tmp)
                LOG.debug("Executing: %s", args)
                process = subprocess.Popen(
                    args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    encoding="utf-8",
                    errors="replace",
                    start_new_session=True,
                )
                processes[process] = ref
                echo(f"  started {ref.label()}")

            while processes:
                for process, ref in list(processes.items()):
                    try:
                        stdout, stderr = process.communicate(timeout=0.1)
                    except subprocess.TimeoutExpired:
                        continue
                    if process.returncode:
                        echo(f"  failed {ref.label()}")
                        error = subprocess.CalledProcessError(
                            process.returncode,
                            process.args,
                            output=stdout,
                            stderr=stderr,
                        )
                        raise RuntimeError(
                            f"App install failed:\n{ref.name}: {error}"
                            f"\nstdout:\n{stdout}\nstderr:\n{stderr}"
                        ) from error
                    echo(stdout, nl=False)
                    echo(stderr, err=True, nl=False)
                    del processes[process]
                    echo(f"  ready {ref.label()}")
        finally:
            stop_helm_processes(list(processes))


def stop_helm_processes(processes: Sequence[subprocess.Popen[str]]) -> None:
    """Terminate all siblings before waiting, with one shared grace period."""
    try:
        for process in processes:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
        deadline = monotonic() + _HELM_TERMINATION_GRACE_SECONDS
        for process in processes:
            with suppress(subprocess.TimeoutExpired):
                process.communicate(timeout=max(0.0, deadline - monotonic()))
    finally:
        # A descendant may survive even when its Helm parent has exited.
        for process in processes:
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
        for process in processes:
            process.communicate()


def helm_install_args(profile: Profile, ref: ChartRef, tmp: Path) -> list[str]:
    args = [
        "helm",
        "upgrade",
        "--install",
        ref.name,
        ref.chart,
        "--version",
        ref.version,
        "--namespace",
        profile.namespace,
        "--wait",
        "--rollback-on-failure",
        f"--timeout={APP_HELM_TIMEOUT}",
    ]
    values = profile.apps.get(ref.name)
    if values:
        values_path = tmp / f"{ref.name}-values.yaml"
        values_path.write_text(
            yaml.safe_dump(values, default_flow_style=False),
            encoding="utf-8",
        )
        args.extend(["-f", str(values_path)])
    return args


def apply_deployment_terraform(profile: Profile, deployments_root: Path | None) -> None:
    state = profile_tf_dir(profile.metadata.name) / "terraform.tfstate"
    if not profile.runtime.databases and not state.is_file():
        return
    root = generate_profile_terraform_root(profile, deployments_root)
    echo(f"Applying Terraform runtime databases in {root}")
    apply_terraform(root, profile.namespace, state=state)


def apply_runtime_manifests(profile: Profile) -> None:
    source_dir = require_source_dir(profile)
    if not profile.runtime.manifests:
        return
    echo(f"Applying {len(profile.runtime.manifests)} runtime manifest group(s)")
    for group in profile.runtime.manifests:
        for relative in group.files:
            path = resolve_path(source_dir, relative)
            echo(f"  kubectl apply -f {path} -n {group.namespace}")
            kubectl(
                "apply",
                f"--namespace={group.namespace}",
                "-f",
                str(path),
            )


def apply_deployment_secrets(profile: Profile) -> None:
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


def apply_deployment(
    profile: Profile,
    *,
    allow_reuse: bool = False,
    image_archive: Path | None = None,
) -> None:
    """Materialize a Deployment from a Profile."""
    result = preflight(profile)
    ensure_kind_cluster(
        profile, allow_reuse=allow_reuse, host_mounts=result.host_mounts
    )
    if image_archive is not None:
        echo(f"Loading image archive into {profile.metadata.name!r}: {image_archive}")
        cluster.load_image_archive(image_archive, cluster_name=profile.metadata.name)

    echo(f"Ensuring namespace {profile.namespace!r}")
    if not resource_exists("namespace", profile.namespace):
        kubectl("create", "namespace", profile.namespace)

    echo("Installing k8s components")
    cluster.apply_builtin_storage_classes()
    cluster.add_helm_repos(profile.k8s.helm_repos)
    cluster.install_helm_components(
        profile.k8s.components, source_dir=profile.source_dir
    )

    echo(f"Ensuring image-pull secret in {profile.namespace!r}")
    create_image_pull_secret(profile.namespace)
    apply_deployment_secrets(profile)

    apply_deployment_terraform(profile, result.deployments_root)
    apply_runtime_manifests(profile)
    install_distribution_apps(profile, result.refs)
