import json
import logging
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.support.execution import FakeExecuteFactory
from tests.support.fixtures import PrepareKind
from zep_dev.cli import cli
from zep_dev.development_environments import discovery, kind, kubernetes
from zep_dev.development_environments.target import ExecutionTarget, execution_target


@pytest.fixture
def target(state_home: Path) -> ExecutionTarget:
    return execution_target("integration")


def service(
    namespace: str,
    name: str,
    *ports: kubernetes.ServicePort,
    traffic_policy: str = "Cluster",
) -> kubernetes.Service:
    return kubernetes.Service(
        metadata=kubernetes.ServiceMetadata(name=name, namespace=namespace),
        spec=kubernetes.ServiceSpec(
            externalTrafficPolicy=traffic_policy, ports=list(ports)
        ),
    )


def port(number: int, name: str, node_port: int) -> kubernetes.ServicePort:
    return kubernetes.ServicePort(port=number, name=name, nodePort=node_port)


def binding(host_ip: str, host_port: int) -> dict[str, str]:
    return {"HostIp": host_ip, "HostPort": str(host_port)}


@pytest.mark.usefixtures("cli_environment")
def test_describe_addresses_published_service_ports_in_every_namespace(
    target: ExecutionTarget,
    prepare_kind: PrepareKind,
    fake_execute: FakeExecuteFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    services = [
        service(
            "applications",
            "web",
            port(80, "http", 30080),
            port(9090, "metrics", 31128),  # Not published.
        ),
        service("monitoring", "web", port(3000, "", 30300)),
    ]
    node = f"{target.cluster_name}-control-plane"
    bindings = {
        "30080/tcp": [binding("127.0.0.1", 8080)] * 2,
        "30300/tcp": [binding("0.0.0.0", 3000)],
        "6443/tcp": [binding("127.0.0.1", 34097)],
    }
    prepare_kind(present=True, name=target.name).on(
        "kind", "get", "nodes", "--name", target.cluster_name, stdout=node + "\n"
    ).on("podman", "inspect", node, stdout=json.dumps(bindings))
    kube_calls = fake_execute(kubernetes).on(
        "kubectl",
        stdout=json.dumps({"items": [item.model_dump() for item in services]}),
    )

    result = CliRunner().invoke(cli, ["environment", "describe", target.name])

    assert result.exit_code == 0, result.exception
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []
    assert json.loads(result.stdout) == {
        "name": target.name,
        "kubernetes": {
            "kubeconfig": str(target.kubeconfig),
            "context": target.context,
            "namespace": target.namespace,
        },
        "addresses": {
            "applications": {"web": {"http": "127.0.0.1:8080"}},
            "monitoring": {"web": {"3000": "127.0.0.1:3000"}},
        },
    }
    assert "--all-namespaces" in kube_calls.calls[0].args


@pytest.mark.usefixtures("cli_environment")
def test_discovery_failure_emits_no_partial_json(
    target: ExecutionTarget,
    prepare_kind: PrepareKind,
    fake_execute: FakeExecuteFactory,
) -> None:
    prepare_kind(present=True, name=target.name)
    failure = subprocess.CalledProcessError(1, ["kubectl", "get"])
    fake_execute(kubernetes).on("kubectl", raises=failure)

    result = CliRunner().invoke(cli, ["environment", "describe", target.name])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "returned non-zero exit status 1" in result.stderr


@pytest.mark.parametrize(
    ("services", "warning"),
    [
        (
            [
                service(
                    "applications",
                    "web",
                    port(80, "http", 30080),
                    traffic_policy="Local",
                )
            ],
            "Ignoring applications/web:http: externalTrafficPolicy=Local",
        ),
        ([], "Ignoring published node port 30080: no Service owns it"),
    ],
    ids=["local-traffic-policy", "no-owning-service"],
)
def test_unaddressable_published_ports_are_omitted_with_a_warning(
    services: list[kubernetes.Service],
    warning: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    published = [kind.PublishedPort("node", 30080, "127.0.0.1:8080")]
    assert discovery.published_addresses(services, published) == {}
    assert caplog.record_tuples == [(discovery.LOG.name, logging.WARNING, warning)]


def test_ambiguous_addresses_identify_conflicting_nodes() -> None:
    published = [
        kind.PublishedPort("first", 30080, "127.0.0.1:8080"),
        kind.PublishedPort("second", 30080, "127.0.0.1:8081"),
    ]
    with pytest.raises(
        ValueError,
        match="Ambiguous address for applications/web:http: "
        "127.0.0.1:8080 via first; 127.0.0.1:8081 via second",
    ):
        discovery.published_addresses(
            [service("applications", "web", port(80, "http", 30080))], published
        )
