"""Describe the addresses an existing Environment publishes on the host."""

import logging
from collections.abc import Sequence
from typing import TypedDict

from zep_dev.development_environments import kind, kubernetes
from zep_dev.development_environments.target import ExecutionTarget

LOG = logging.getLogger(__name__)


class KubernetesConnection(TypedDict):
    kubeconfig: str
    context: str
    namespace: str


# Namespace -> Service -> Service port name (or number when unnamed) -> host:port.
type Addresses = dict[str, dict[str, dict[str, str]]]


class EnvironmentDescription(TypedDict):
    name: str
    kubernetes: KubernetesConnection
    addresses: Addresses


def _port_key(port: kubernetes.ServicePort) -> str:
    return port.name or str(port.port)


def published_addresses(
    services: Sequence[kubernetes.Service], published: Sequence[kind.PublishedPort]
) -> Addresses:
    """Address each published node port through the Service port that owns it."""
    candidates: dict[int, dict[str, set[str]]] = {}  # node port -> address -> nodes
    for binding in published:
        nodes_by_address = candidates.setdefault(binding.node_port, {})
        nodes_by_address.setdefault(binding.address, set()).add(binding.node)
    addresses: Addresses = {}
    for service in sorted(
        services, key=lambda item: (item.metadata.namespace, item.metadata.name)
    ):
        metadata, spec = service.metadata, service.spec
        for port in sorted(spec.ports, key=_port_key):
            if port.protocol != "TCP" or port.nodePort not in candidates:
                continue
            bindings = candidates.pop(port.nodePort)
            key = _port_key(port)
            connection = f"{metadata.namespace}/{metadata.name}:{key}"
            if spec.externalTrafficPolicy != "Cluster":
                LOG.warning(
                    "Ignoring %s: externalTrafficPolicy=%s",
                    connection,
                    spec.externalTrafficPolicy,
                )
                continue
            if len(bindings) > 1:
                conflicts = "; ".join(
                    f"{address} via {', '.join(sorted(nodes))}"
                    for address, nodes in sorted(bindings.items())
                )
                raise ValueError(f"Ambiguous address for {connection}: {conflicts}")
            (address,) = bindings
            ports = addresses.setdefault(metadata.namespace, {}).setdefault(
                metadata.name, {}
            )
            ports[key] = address
    for node_port in sorted(candidates):
        LOG.warning("Ignoring published node port %s: no Service owns it", node_port)
    return addresses


def describe_environment(target: ExecutionTarget) -> EnvironmentDescription:
    return {
        "name": target.name,
        "kubernetes": {
            "kubeconfig": str(target.kubeconfig),
            "context": target.context,
            "namespace": target.namespace,
        },
        "addresses": published_addresses(
            kubernetes.observe_services(target), kind.observe_published_ports(target)
        ),
    }
