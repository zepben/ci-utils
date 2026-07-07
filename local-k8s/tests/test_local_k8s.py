import os
from io import StringIO
from pathlib import Path

import pytest
from pydantic import ValidationError

from local_k8s.cluster import (
    KUBECONF_PATH,
    kube_guard,
)
from local_k8s.models import ClusterComponents

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_examples_components_yaml_parses() -> None:
    components = ClusterComponents.from_text_io(
        (EXAMPLES / "components.yaml").open(encoding="utf-8")
    )

    assert components.helm_repos == {
        "argocd": "https://argoproj.github.io/argo-helm",
    }
    assert len(components.cluster_components) == 1

    argocd = components.cluster_components[0]
    assert argocd.name == "argocd"
    assert argocd.chart == "argocd/argo-cd"
    assert argocd.version == "10.0.1"
    assert argocd.namespace == "argocd"
    assert argocd.set["server.service.type"] == "NodePort"


def test_empty_cluster_components_valid() -> None:
    yaml_input = """\
helm_repos:
  argocd: "https://argoproj.github.io/argo-helm"
cluster_components: []
"""
    components = ClusterComponents.from_text_io(StringIO(yaml_input))

    assert components.helm_repos == {
        "argocd": "https://argoproj.github.io/argo-helm",
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
