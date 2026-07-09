from pathlib import Path

import pytest

import local_k8s.shared as shared
from local_k8s.shared import resolve


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setattr(shared, "get_bin_dir", lambda: d)
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
