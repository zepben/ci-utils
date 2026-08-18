import os
from collections.abc import Callable
from io import StringIO
from itertools import pairwise
from pathlib import Path
from types import ModuleType

import pytest
import yaml
from pydantic import ValidationError

from _fake_execute import FakeExecute
from zep_dev import cluster
from zep_dev.k8s import (
    KUBECONF_PATH,
    kube_guard,
)
from zep_dev.models import (
    ClusterComponent,
    ClusterComponents,
    ConfigMapFromFile,
    LocalRepo,
    LocalRepoIntegration,
    OciRepository,
)

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_examples_components_yaml_parses() -> None:
    components = ClusterComponents.from_text_io(
        (EXAMPLES / "components.yaml").open(encoding="utf-8")
    )

    assert components.helm_repos == {
        "argo": "https://argoproj.github.io/argo-helm",
    }
    [argo_cd] = components.cluster_components
    assert argo_cd.name == "argo-cd"
    assert argo_cd.chart == "argo/argo-cd"
    assert argo_cd.version == "9.5.0"
    assert argo_cd.namespace == "argo-cd"
    assert argo_cd.local_repo_integration == LocalRepoIntegration(type="argo-cd")
    assert argo_cd.config_maps_from_file == [
        ConfigMapFromFile(
            name="kind-cluster-config",
            from_file={"kind-cluster.yaml": "kind-cluster.yaml"},
        )
    ]
    assert argo_cd.values["server"]["service"]["type"] == "NodePort"
    assert argo_cd.values["configs"]["cm"]["admin.enabled"] is True
    assert argo_cd.values["dex"]["enabled"] is False


def test_empty_cluster_components_valid() -> None:
    yaml_input = """\
helm_repos:
  argo: "https://argoproj.github.io/argo-helm"
cluster_components: []
"""
    components = ClusterComponents.from_text_io(StringIO(yaml_input))

    assert components.helm_repos == {
        "argo": "https://argoproj.github.io/argo-helm",
    }
    assert components.cluster_components == []


def test_rejects_unknown_top_level_field() -> None:
    yaml_input = """\
helm_repos: {}
cluster_components: []
unknown_field: true
"""
    with pytest.raises(ValidationError):
        ClusterComponents.from_text_io(StringIO(yaml_input))


def test_cluster_components_from_path_sets_source_dir(
    tmp_path: Path,
) -> None:
    components_path = tmp_path / "components.yaml"
    components_path.write_text(
        """\
helm_repos: {}
cluster_components:
  - name: database
    chart: example/database
    version: "1.0.0"
    namespace: test
    config_maps_from_file:
      - name: database-init
        from_file:
          init.sql: ../sql/init.sql
"""
    )

    from_path = ClusterComponents.from_path(components_path)
    from_text = ClusterComponents.from_text_io(StringIO(components_path.read_text()))

    assert from_path.source_dir == tmp_path.resolve()
    assert from_text.source_dir is None
    assert from_path.cluster_components[0].config_maps_from_file[0].from_file == {
        "init.sql": "../sql/init.sql",
    }


def test_config_map_from_file_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ConfigMapFromFile.model_validate(
            {
                "name": "database-init",
                "from_file": {"init.sql": "init.sql"},
                "unexpected": True,
            }
        )


def test_cluster_component_rejects_duplicate_config_map_names() -> None:
    with pytest.raises(ValidationError, match="duplicate config_maps_from_file name"):
        ClusterComponent.model_validate(
            {
                "name": "database",
                "chart": "example/database",
                "version": "1.0.0",
                "namespace": "test",
                "config_maps_from_file": [
                    {"name": "database-init", "from_file": {"init.sql": "init.sql"}},
                    {
                        "name": "database-init",
                        "from_file": {"seed.sql": "seed.sql"},
                    },
                ],
            }
        )


@pytest.mark.parametrize(
    ("installed", "namespace_exists", "expected_events"),
    [
        ("", False, ["Namespace", "ConfigMap", "helm install"]),
        ("database\n", False, ["Namespace", "ConfigMap"]),
        ("", True, ["ConfigMap", "helm install"]),
        ("database\n", True, ["ConfigMap"]),
    ],
)
def test_install_helm_components_applies_config_maps_before_install_or_skip(
    fake_execute: Callable[[ModuleType], FakeExecute],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    installed: str,
    namespace_exists: bool,
    expected_events: list[str],
) -> None:
    (tmp_path / "init.sql").write_text("SELECT 'ready';\n", encoding="utf-8")
    components_path = tmp_path / "components.yaml"
    components_path.write_text(
        """\
helm_repos: {}
cluster_components:
  - name: database
    chart: example/database
    version: "1.0.0"
    namespace: test
    config_maps_from_file:
      - name: database-init
        from_file:
          init.sql: init.sql
"""
    )
    components = ClusterComponents.from_path(components_path)
    events: list[str] = []
    config_maps: list[dict[str, object]] = []
    resource_exists_calls: list[tuple[str, str]] = []
    fake_helm = fake_execute(cluster)
    fake_helm.on("helm", "list", stdout=installed)
    if not installed:
        fake_helm.on(
            "helm",
            "install",
            "database",
            hook=lambda _args, _kwargs: events.append("helm install"),
        )

    def record_create_namespace(
        _args: tuple[str, ...], _kwargs: dict[str, object]
    ) -> None:
        events.append("Namespace")

    def record_apply(_args: tuple[str, ...], kwargs: dict[str, object]) -> None:
        manifest = yaml.safe_load(str(kwargs["input"]))
        events.append(manifest["kind"])
        if manifest["kind"] == "ConfigMap":
            config_maps.append(manifest)

    def fake_resource_exists(resource: str, name: str, **kwargs: object) -> bool:
        resource_exists_calls.append((resource, name))
        return namespace_exists

    fake_kubectl = (
        FakeExecute()
        .on("create", "namespace", hook=record_create_namespace)
        .on("apply", "-f", "-", hook=record_apply)
    )
    monkeypatch.setattr(cluster, "resource_exists", fake_resource_exists)
    monkeypatch.setattr(cluster, "kubectl", fake_kubectl)

    cluster.install_helm_components(components)

    assert resource_exists_calls == [("namespace", "test")]
    assert events == expected_events
    assert config_maps == [
        {
            "apiVersion": "v1",
            "kind": "ConfigMap",
            "metadata": {"name": "database-init", "namespace": "test"},
            "data": {"init.sql": "SELECT 'ready';\n"},
        }
    ]


def test_kube_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    og_kube = "something"
    monkeypatch.setenv("KUBECONFIG", og_kube)

    with kube_guard():
        assert os.environ["KUBECONFIG"] == str(KUBECONF_PATH)

    assert os.environ.get("KUBECONFIG") == og_kube


def test_add_helm_repos_skips_all_helm_when_no_repos_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    def fake_helm(*args: str) -> str:
        raise AssertionError(f"unexpected helm invocation: {args}")

    monkeypatch.setattr(cluster, "helm", fake_helm)
    cluster.add_helm_repos(
        ClusterComponents(helm_repos={}, cluster_components=[]),
    )


def test_install_helm_components_applies_local_repo_integration_only_to_selected_component(
    fake_execute: Callable[[ModuleType], FakeExecute],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    installed_values: dict[str, list[object]] = {}
    reconciled_components: list[str] = []

    def capture_values(args: tuple[str, ...], kwargs: dict[str, object]) -> None:
        _, _, release, *_ = args
        value_paths = [Path(value) for flag, value in pairwise(args) if flag == "-f"]
        installed_values[release] = [
            yaml.safe_load(path.read_text(encoding="utf-8")) for path in value_paths
        ]

    fake = fake_execute(cluster)
    fake.on("helm", "list", stdout="")
    fake.on("helm", "install", "argo", hook=capture_values)
    fake.on("helm", "install", "other", hook=capture_values)
    monkeypatch.setattr(
        cluster,
        "apply_argo_oci_repository_secrets",
        lambda namespace, _repositories: reconciled_components.append(namespace),
    )
    components = ClusterComponents(
        helm_repos={},
        cluster_components=[
            ClusterComponent(
                name="argo",
                chart="example/argo",
                version="1.0.0",
                namespace="argo",
                local_repo_integration=LocalRepoIntegration(type="argo-cd"),
                values={"base": "argo"},
            ),
            ClusterComponent(
                name="other",
                chart="example/other",
                version="1.0.0",
                namespace="other",
                values={"base": "other"},
            ),
        ],
    )

    cluster.install_helm_components(
        components,
        local_repos=[LocalRepo(path=tmp_path / "deployments")],
    )

    assert installed_values["other"] == [{"base": "other"}]
    assert reconciled_components == ["argo"]
    base_values, overlay = installed_values["argo"]
    assert base_values == {"base": "argo"}
    assert overlay == {
        "configs": {
            "repositories": {
                "local-deployments": {
                    "name": "deployments",
                    "type": "git",
                    "url": "file:///mnt/local-repos/deployments",
                }
            }
        },
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
                    "mountPath": "/mnt/local-repos",
                    "name": "local-repos",
                    "readOnly": True,
                }
            ],
            "volumes": [
                {
                    "hostPath": {
                        "path": "/mnt/local-repos",
                        "type": "Directory",
                    },
                    "name": "local-repos",
                }
            ],
        },
    }


def test_install_helm_components_refreshes_argo_oci_repositories_when_installed(
    fake_execute: Callable[[ModuleType], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = OciRepository(
        name="private-charts",
        registry="registry.example.com",
        repository="charts",
    )
    reconciled: list[tuple[str, list[OciRepository]]] = []
    fake = fake_execute(cluster)
    fake.on("helm", "list", stdout="argo\n")
    monkeypatch.setattr(
        cluster,
        "apply_argo_oci_repository_secrets",
        lambda namespace, repositories: reconciled.append(
            (namespace, list(repositories))
        ),
    )
    components = ClusterComponents(
        helm_repos={},
        cluster_components=[
            ClusterComponent(
                name="argo",
                chart="example/argo",
                version="1.0.0",
                namespace="argo",
                local_repo_integration=LocalRepoIntegration(
                    type="argo-cd",
                    oci_repositories=[repository],
                ),
            )
        ],
    )

    cluster.install_helm_components(components)

    assert reconciled == [("argo", [repository])]
    assert fake.calls_for("helm", "install") == []
