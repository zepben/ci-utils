"""Describe application connections observed in an existing Environment."""

import sys
from collections.abc import Sequence
from typing import TypedDict

from zep_dev.development_environments import helm, kind, kubernetes
from zep_dev.development_environments.target import ExecutionTarget


class KubernetesConnection(TypedDict):
    kubeconfig: str
    context: str


class ApplicationDescription(TypedDict):
    namespace: str
    endpoints: dict[str, str]


class EnvironmentDescription(TypedDict):
    name: str
    kubernetes: KubernetesConnection
    applications: dict[str, ApplicationDescription]


type HttpService = tuple[str, kubernetes.Service, int]


def http_services(
    applications: Sequence[helm.ApplicationRelease],
    services: Sequence[kubernetes.Service],
) -> list[HttpService]:
    releases: dict[str, helm.ApplicationRelease] = {}
    for application in applications:
        previous = releases.get(application.chart)
        if previous is not None:
            raise ValueError(
                f"Multiple releases of application {application.chart!r}: "
                f"{previous.namespace}/{previous.name}, "
                f"{application.namespace}/{application.name}"
            )
        releases[application.chart] = application
    exposed: list[HttpService] = []
    for service in services:
        metadata, spec = service.metadata, service.spec
        release = releases.get(metadata.labels.get("app.kubernetes.io/name", ""))
        if release is None:
            continue
        if (
            metadata.namespace != release.namespace
            or metadata.annotations.get("meta.helm.sh/release-name") != release.name
            or metadata.annotations.get("meta.helm.sh/release-namespace")
            != release.namespace
        ):
            continue
        if spec.type != "NodePort":
            continue
        for port in spec.ports:
            if port.name != "http" or port.protocol != "TCP" or port.nodePort is None:
                continue
            if spec.externalTrafficPolicy != "Cluster":
                print(
                    f"Ignoring unsupported HTTP Service {metadata.namespace}/{metadata.name}: "
                    f"externalTrafficPolicy={spec.externalTrafficPolicy}",
                    file=sys.stderr,
                )
                continue
            exposed.append((release.chart, service, port.nodePort))
    return exposed


def assemble_description(
    target: ExecutionTarget,
    applications: Sequence[helm.ApplicationRelease],
    services: Sequence[HttpService],
    mappings: Sequence[kind.PublishedPort],
) -> EnvironmentDescription:
    descriptions: dict[str, ApplicationDescription] = {
        application.chart: {"namespace": application.namespace, "endpoints": {}}
        for application in sorted(applications, key=lambda item: item.chart)
    }
    candidates: dict[str, dict[str, set[str]]] = {}
    for application, service, node_port in services:
        for mapping in mappings:
            if mapping.node_port != node_port:
                continue
            url = f"http://{mapping.host_ip}:{mapping.host_port}"
            source = f"{service.metadata.namespace}/{service.metadata.name} via {mapping.node}:{node_port}"
            candidates.setdefault(application, {}).setdefault(url, set()).add(source)
    for application, urls in sorted(candidates.items()):
        if len(urls) > 1:
            conflicts = "; ".join(
                f"{url} ({', '.join(sorted(sources))})"
                for url, sources in sorted(urls.items())
            )
            raise ValueError(
                f"Ambiguous HTTP endpoint for application {application!r}: {conflicts}"
            )
        descriptions[application]["endpoints"]["http"] = next(iter(urls))
    return {
        "name": target.name,
        "kubernetes": {"kubeconfig": str(target.kubeconfig), "context": target.context},
        "applications": descriptions,
    }


def describe_environment(target: ExecutionTarget) -> EnvironmentDescription:
    applications = helm.observe_applications(target)
    exposed = http_services(
        applications, kubernetes.observe_services(target) if applications else []
    )
    mappings = kind.observe_published_ports(target) if exposed else []
    return assemble_description(target, applications, exposed, mappings)
