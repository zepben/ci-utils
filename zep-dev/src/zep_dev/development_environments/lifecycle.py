"""Lifecycle policy for named development Environments.

The Template is needed for creation only. Destruction and kubeconfig lookup use
validated identity and conventionally derived operational paths.
"""

import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import assert_never

from pydantic import ValidationError

from zep_dev.development_environments import (
    argo,
    cnpg,
    diagnostics,
    documents,
    helm,
    kind,
    kubernetes,
    local_inputs,
    manifests,
    secrets,
    supporting,
    terraform,
)
from zep_dev.development_environments.chart_sources import ChartRef, ChartResolver
from zep_dev.development_environments.distributions import (
    GHCR_REGISTRY,
    ChartName,
)
from zep_dev.development_environments.names import CLUSTER_PREFIX
from zep_dev.development_environments.services import (
    CnpgService,
    HelmService,
    RawService,
)
from zep_dev.development_environments.target import (
    ExecutionTarget,
    environment_name,
    execution_target,
)
from zep_dev.development_environments.templates import EnvironmentTemplate
from zep_dev.errors import ZepDevError


@dataclass(frozen=True)
class CreationPlan:
    template: EnvironmentTemplate
    target: ExecutionTarget
    inputs: local_inputs.ResolvedInputs
    mounts: tuple[kind.HostMount, ...]
    kind_config: str
    charts: tuple[ChartRef, ...]
    config_maps: dict[str, tuple[supporting.ResolvedConfigMap, ...]]
    application_manifests: tuple[Path, ...]
    runtime_applications: tuple[terraform.RuntimeApplication, ...]


def list_environments() -> list[str]:
    """List live Kind clusters owned by valid Environment names."""
    names: set[str] = set()
    for cluster in kind.list_clusters():
        if not cluster.startswith(CLUSTER_PREFIX):
            continue
        try:
            names.add(environment_name(cluster.removeprefix(CLUSTER_PREFIX)))
        except ValidationError:
            continue
    return sorted(names)


def preflight(template_path: Path, image_archive: Path | None = None) -> CreationPlan:
    """Resolve required inputs before observing or mutating the Kind cluster."""
    template, distribution = documents.load_template(template_path)
    target = execution_target(template.metadata.name)

    config_maps = {
        name: supporting.resolve_config_maps(
            template_path, service.config_maps_from_file
        )
        for name, service in template.services.items()
        if isinstance(service, HelmService)
    }
    application_manifests = manifests.resolve_application_manifests(
        template_path, template
    )

    inputs = local_inputs.load_required_inputs(template)
    mounts = tuple(
        kind.HostMount(inputs.mounts[mount.slot], mount.node_path)
        for mount in template.cluster.mounts
    ) + argo.repository_mounts(inputs.argo_repositories)
    kind_config = kind.render_kind_config(template.cluster.kind, mounts)
    if image_archive is not None and (
        not image_archive.is_file() or image_archive.stat().st_size == 0
    ):
        raise ZepDevError(f"image archive is missing or empty: {image_archive}")

    charts: tuple[ChartRef, ...] = ()
    kind_wrappers: dict[ChartName, Path | str] = {}
    if distribution is not None:
        resolver = ChartResolver()
        resolved = resolver.resolve_all(distribution.charts)
        published = resolver.check_all(resolved)
        secrets.resolve_registry_credential(GHCR_REGISTRY)
        charts = tuple(resolved)
        for ref, chart in zip(resolved, published, strict=True):
            module = resolver.kind_wrapper(ref, chart)
            application = template.applications.get(ref.name)
            if module is not None:
                kind_wrappers[ref.name] = module
            elif application is not None and application.databases:
                raise ZepDevError(
                    f"applications.{ref.name}.databases is declared, but no Kind "
                    f"wrapper was found for {ref.label()}: its revision has none, or "
                    "it was published without its source commit"
                )
    runtime_applications = terraform.resolve_runtime_applications(
        target, template, kind_wrappers
    )
    for service in template.services.values():
        if isinstance(service, HelmService) and service.integration is not None:
            for repository in service.integration.oci_repositories:
                secrets.resolve_registry_credential(repository.registry)
    return CreationPlan(
        template=template,
        target=target,
        inputs=inputs,
        mounts=mounts,
        kind_config=kind_config,
        charts=charts,
        config_maps=config_maps,
        application_manifests=application_manifests,
        runtime_applications=runtime_applications,
    )


def provision_services(plan: CreationPlan) -> None:
    target = plan.target
    releases: Mapping[tuple[str, str], str] | None = None
    for name, service in plan.template.services.items():
        match service:
            case CnpgService():
                namespace = target.namespace_for(service.namespace)
                if namespace != target.namespace:
                    kubernetes.ensure_namespace(target, namespace)
                cnpg.apply_cnpg_service(target, name, service)
            case RawService():
                supporting.apply_raw_service(target, service)
            case HelmService():
                if releases is None:
                    releases = helm.release_statuses(target)
                provision_helm_service(plan, name, service, releases)
            case _:
                assert_never(service)


def provision_helm_service(
    plan: CreationPlan,
    name: str,
    service: HelmService,
    releases: Mapping[tuple[str, str], str],
) -> None:
    target = plan.target
    namespace = target.namespace_for(service.namespace)
    if configs := plan.config_maps[name]:
        kubernetes.ensure_namespace(target, namespace)
        supporting.apply_config_maps(target, namespace, configs)
    status = releases.get((namespace, name))
    if status is None or status == "uninstalled":
        repositories = (
            [
                plan.inputs.argo_repositories[key]
                for key in service.integration.repositories
            ]
            if service.integration is not None
            else []
        )
        helm.install_service(
            target, name, service, argo.repository_overlay(repositories)
        )
    elif status != "deployed":
        raise ZepDevError(
            f"Supporting Helm release {name!r} in namespace {namespace!r} has "
            f"status {status!r} (Environment {target.name!r}). Destroy the "
            f"Environment or uninstall the release before retrying."
        )
    supporting.wait_for_resources(target, service)
    supporting.apply_load_db_credentials(target, service)
    if service.integration is not None:
        for repository in service.integration.oci_repositories:
            secrets.apply_argo_oci_repository_secret(target, namespace, repository)


def create_environment(
    template_path: Path,
    *,
    allow_reuse: bool = False,
    image_archive: Path | None = None,
) -> ExecutionTarget:
    """Create or explicitly reuse an Environment; retain partial work on failure."""
    plan = preflight(template_path, image_archive)
    target = plan.target
    exists = kind.cluster_exists(target)
    if exists:
        if not allow_reuse:
            raise ZepDevError(
                f"Kind cluster {target.cluster_name!r} already exists; "
                "destroy it or pass allow_reuse=True"
            )
        if plan.mounts:
            kind.validate_existing_worker_mounts(target, plan.mounts)
        if target.kubeconfig.is_symlink():
            raise ZepDevError(
                f"Environment kubeconfig is a symlink: {target.kubeconfig}"
            )
        kind.export_kubeconfig(target)
    else:
        if target.directory.is_symlink():
            raise ZepDevError(f"Environment directory is a symlink: {target.directory}")
        if target.directory.exists():
            print(
                f"Removing stale Environment files at {target.directory}",
                file=sys.stderr,
            )
            shutil.rmtree(target.directory)
        kind.create_cluster(target, plan.kind_config)

    try:
        if image_archive is not None:
            kind.load_image_archive(target, image_archive)
        kubernetes.ensure_namespace(target, target.namespace)
        kubernetes.apply_builtin_storage_classes(target)
        provision_services(plan)
        if plan.charts:
            secrets.create_image_pull_secret(target, target.namespace)
        for key, secret in plan.template.inputs.secrets.items():
            secrets.create_bound_secret(target, secret.name, plan.inputs.secrets[key])
        terraform.apply_runtime(target, plan.runtime_applications)
        manifests.apply_application_manifests(target, plan.application_manifests)
        helm.install_applications(
            target,
            plan.charts,
            {
                name: config.values
                for name, config in plan.template.applications.items()
            },
        )
    except Exception:
        if os.getenv("CI_DUMP_DEBUG"):
            print(
                f"Environment {target.name} provisioning failed; collecting debug dump",
                file=sys.stderr,
                flush=True,
            )
            try:
                diagnostics.take_debug_dump(target)
            except Exception as error:
                print(f"Debug dump failed: {error}", file=sys.stderr, flush=True)
        raise
    return target


def destroy_environment(name: str) -> None:
    """Ensure the named cluster is absent before removing only its owned files."""
    target = execution_target(name)
    if target.directory.is_symlink():
        raise ZepDevError(f"Environment directory is a symlink: {target.directory}")
    if kind.cluster_exists(target):
        kind.delete_cluster(target)
    if target.directory.exists():
        shutil.rmtree(target.directory)


def require_environment(name: str) -> ExecutionTarget:
    target = execution_target(name)
    if not kind.cluster_exists(target):
        raise ZepDevError(f"Kind cluster {target.cluster_name!r} does not exist")
    if target.kubeconfig.is_symlink():
        raise ZepDevError(f"Environment kubeconfig is a symlink: {target.kubeconfig}")
    if not target.kubeconfig.is_file():
        kind.export_kubeconfig(target)
    return target


def environment_kubeconfig(name: str) -> Path:
    """Return a live cluster's kubeconfig, regenerating its owned file if absent."""
    return require_environment(name).kubeconfig
