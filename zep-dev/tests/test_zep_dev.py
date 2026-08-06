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
from zep_dev.cluster import (
    KUBECONF_PATH,
    kube_guard,
)
from zep_dev.models import ClusterComponent, ClusterComponents, LocalRepo

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
    assert argo_cd.local_repo_integration == "argo-cd"
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
    cluster._add_helm_repos(
        ClusterComponents(helm_repos={}, cluster_components=[]),
    )


def test_install_helm_components_applies_local_repo_integration_only_to_selected_component(
    fake_execute: Callable[[ModuleType], FakeExecute],
    tmp_path: Path,
) -> None:
    installed_values: dict[str, list[object]] = {}

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
    components = ClusterComponents(
        helm_repos={},
        cluster_components=[
            ClusterComponent(
                name="argo",
                chart="example/argo",
                version="1.0.0",
                namespace="argo",
                local_repo_integration="argo-cd",
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

    cluster._install_helm_components(
        components,
        local_repos=[LocalRepo(path=tmp_path / "deployments")],
    )

    assert installed_values["other"] == [{"base": "other"}]
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
