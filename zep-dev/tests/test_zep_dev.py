import os
from io import StringIO
from pathlib import Path

import pytest
from pydantic import ValidationError

from zep_dev import cluster
from zep_dev.cluster import (
    KUBECONF_PATH,
    kube_guard,
)
from zep_dev.models import ClusterComponents

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_examples_components_yaml_parses() -> None:
    components = ClusterComponents.from_text_io(
        (EXAMPLES / "components.yaml").open(encoding="utf-8")
    )

    assert components.helm_repos == {
        "argo": "https://argoproj.github.io/argo-helm",
    }
    assert len(components.cluster_components) == 1

    argo_cd = components.cluster_components[0]
    assert argo_cd.name == "argo-cd"
    assert argo_cd.chart == "argo/argo-cd"
    assert argo_cd.version == "9.5.0"
    assert argo_cd.namespace == "argo-cd"
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
