from pathlib import Path

import pytest

import local_k8s.shared as shared
from local_k8s.shared import ResolvedChart, resolve, resolve_chart


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setattr(shared, "get_bin_dir", lambda: d)
    monkeypatch.setenv("PATH", f"{d}:{tmp_path}")
    return d


@pytest.fixture
def kind_binary(bin_dir: Path) -> Path:
    tool = bin_dir / "kind"
    tool.write_text("#!/bin/sh\n")
    tool.chmod(0o755)
    return tool


def test_resolve_missing(bin_dir: Path) -> None:
    with pytest.raises(Exception, match="not installed"):
        resolve("kind")


def test_resolve_not_executable(bin_dir: Path) -> None:
    (bin_dir / "kind").write_text("data")
    with pytest.raises(Exception, match="not installed"):
        resolve("kind")


def test_resolve_unknown(bin_dir: Path) -> None:
    with pytest.raises(Exception, match="Failed to locate tool"):
        resolve("nosuch")


def test_resolve_chart_accepts_repo_root_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helm_dir = (tmp_path / "helm").resolve()
    chart_dir = helm_dir / "charts" / "myapp"
    chart_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    result = resolve_chart(helm_dir, Path("helm/charts/myapp"))

    assert result == ResolvedChart(
        absolute_path=chart_dir,
        path_relative_to_helm_dir=Path("charts/myapp"),
    )


def test_resolve_chart_outside_helm_dir_raises(tmp_path: Path) -> None:
    helm_dir = (tmp_path / "helm").resolve()
    helm_dir.mkdir()
    outside_chart = (tmp_path / "other" / "myapp").resolve()

    with pytest.raises(Exception, match="not inside --helm-dir"):
        resolve_chart(helm_dir, outside_chart)
