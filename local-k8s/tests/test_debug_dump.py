from pathlib import Path

import pytest

from local_k8s.cluster import dump_to_stdout


@pytest.mark.parametrize(
    ("filter_namespaces", "included", "excluded"),
    [
        ([], ["ks-manifest", "argo-manifest"], []),
        (["argocd"], ["argo-manifest"], ["ks-manifest"]),
    ],
)
def test_dump_to_stdout_namespace_filter(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    filter_namespaces: list[str],
    included: list[str],
    excluded: list[str],
) -> None:
    (tmp_path / "kube-system").mkdir()
    (tmp_path / "kube-system" / "pod.yaml").write_text("ks-manifest\n")
    (tmp_path / "argocd").mkdir()
    (tmp_path / "argocd" / "deploy.yaml").write_text("argo-manifest\n")

    dump_to_stdout(filter_namespaces, tmp_path)
    out = capsys.readouterr().out

    for text in included:
        assert text in out
    for text in excluded:
        assert text not in out


def test_dump_to_stdout_file_selection(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "noise.txt").write_text("noise\n")
    namespace = tmp_path / "kube-system"
    namespace.mkdir()
    (namespace / "manifest.yaml").write_text("manifest\n")
    (namespace / "root.txt").write_text("root-txt\n")
    pod = namespace / "pod-name"
    pod.mkdir()
    (pod / "logs.txt").write_text("pod-logs\n")
    (pod / "readme.md").write_text("extra\n")

    dump_to_stdout([], tmp_path)
    out = capsys.readouterr().out

    assert "manifest" in out
    assert "pod-logs" in out
    assert "noise" not in out
    assert "root-txt" not in out
    assert "extra" not in out
