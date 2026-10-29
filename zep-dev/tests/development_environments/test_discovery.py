import json
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from tests.support.execution import FakeExecuteFactory, option_value
from tests.support.fixtures import PrepareKind
from zep_dev.cli import cli
from zep_dev.development_environments import discovery, helm, kind, kubernetes
from zep_dev.development_environments.target import ExecutionTarget, execution_target

NODE_PORT = 30191
HOST_PORT = 19191
HOST_IP = "127.0.0.1"


@pytest.fixture
def target(state_home: Path) -> ExecutionTarget:
    return execution_target("integration")


@pytest.fixture
def application() -> helm.ApplicationRelease:
    return helm.ApplicationRelease(
        name="hcs-release", namespace="applications", chart="hcs"
    )


def service(
    application: helm.ApplicationRelease, node_port: int | None
) -> kubernetes.Service:
    return kubernetes.Service(
        metadata=kubernetes.ServiceMetadata(
            name=application.chart,
            namespace=application.namespace,
            labels={"app.kubernetes.io/name": application.chart},
            annotations={
                "meta.helm.sh/release-name": application.name,
                "meta.helm.sh/release-namespace": application.namespace,
            },
        ),
        spec=kubernetes.ServiceSpec(
            type="NodePort" if node_port is not None else "ClusterIP",
            ports=[kubernetes.ServicePort(name="http", nodePort=node_port)],
        ),
    )


@pytest.mark.usefixtures("cli_environment")
def test_describe_discovers_connections_and_excludes_unrelated_services(
    target: ExecutionTarget,
    application: helm.ApplicationRelease,
    prepare_kind: PrepareKind,
    fake_execute: FakeExecuteFactory,
) -> None:
    unexposed = helm.ApplicationRelease(
        name="ewb-release", namespace="workbench", chart="ewb"
    )
    applications = [application, unexposed]
    services = [service(application, NODE_PORT), service(unexposed, None)]
    for offset, change in enumerate(
        [
            {"chart": "hcs-rabbitmq"},
            {"namespace": "unrelated"},
            {"name": "unrelated"},
        ],
        start=1,
    ):
        services.append(
            service(application.model_copy(update=change), NODE_PORT + offset)
        )
    # Publish every distractor; duplicate bindings must collapse to one URL.
    bindings = {
        f"{port.nodePort}/tcp": [
            {"HostIp": HOST_IP, "HostPort": str(HOST_PORT + offset)}
        ]
        * 2
        for offset, candidate in enumerate(services)
        for port in candidate.spec.ports
        if port.nodePort is not None
    }
    node = f"{target.cluster_name}-control-plane"
    prepare_kind(present=True, name=target.name).on(
        "kind",
        "get",
        "nodes",
        "--name",
        target.cluster_name,
        stdout=node + "\n",
    ).on("podman", "inspect", node, stdout=json.dumps(bindings))
    helm_calls = fake_execute(helm).on(
        "helm",
        "list",
        stdout=json.dumps(
            [
                {
                    "name": app.name,
                    "namespace": app.namespace,
                    "revision": "1",
                    "status": "deployed",
                }
                for app in applications
            ]
        ),
    )
    for app in applications:
        helm_calls.on("helm", "get", "metadata", app.name, stdout=app.model_dump_json())
    kube_calls = fake_execute(kubernetes).on(
        "kubectl",
        stdout=json.dumps(
            {
                "items": [candidate.model_dump() for candidate in services],
            }
        ),
    )

    result = CliRunner().invoke(cli, ["environment", "describe", target.name])

    assert result.exit_code == 0, result.exception
    assert result.stderr == ""
    assert json.loads(result.stdout) == {
        "name": target.name,
        "kubernetes": {"kubeconfig": str(target.kubeconfig), "context": target.context},
        "applications": {
            application.chart: {
                "namespace": application.namespace,
                "endpoints": {"http": f"http://{HOST_IP}:{HOST_PORT}"},
            },
            unexposed.chart: {"namespace": unexposed.namespace, "endpoints": {}},
        },
    }
    listing = helm_calls.calls[0]
    assert "--all-namespaces" in listing.args
    assert (
        option_value(listing.args, "--selector")
        == f"zepben.com/environment={target.name}"
    )
    assert "--all-namespaces" in kube_calls.calls[0].args


@pytest.mark.usefixtures("cli_environment")
def test_discovery_failure_emits_no_partial_json(
    target: ExecutionTarget,
    prepare_kind: PrepareKind,
    fake_execute: FakeExecuteFactory,
) -> None:
    prepare_kind(present=True, name=target.name)
    failure = subprocess.CalledProcessError(1, ["helm", "list"])
    fake_execute(helm).on("helm", "list", raises=failure)

    result = CliRunner().invoke(cli, ["environment", "describe", target.name])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert "returned non-zero exit status 1" in result.stderr


def test_duplicate_application_releases_fail_across_namespaces(
    application: helm.ApplicationRelease,
) -> None:
    duplicate = application.model_copy(update={"namespace": "another-namespace"})
    with pytest.raises(ValueError, match="Multiple releases") as failure:
        discovery.http_services([application, duplicate], [])
    for app in (application, duplicate):
        assert f"{app.namespace}/{app.name}" in str(failure.value)


def test_ambiguous_endpoints_identify_conflicting_connections(
    target: ExecutionTarget,
    application: helm.ApplicationRelease,
) -> None:
    mappings = [
        kind.PublishedPort(node, NODE_PORT, HOST_IP, HOST_PORT + offset)
        for offset, node in enumerate(("first", "second"))
    ]
    with pytest.raises(ValueError, match="Ambiguous HTTP endpoint") as failure:
        discovery.assemble_description(
            target,
            [application],
            discovery.http_services([application], [service(application, NODE_PORT)]),
            mappings,
        )
    for mapping in mappings:
        assert f"http://{mapping.host_ip}:{mapping.host_port}" in str(failure.value)
        assert mapping.node in str(failure.value)
