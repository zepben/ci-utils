from pathlib import Path
from unittest.mock import MagicMock

import pytest

import local_k8s.shared as shared
from local_k8s.shared import execute, resolve


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


def test_resolve_executable(kind_binary: Path) -> None:
    assert resolve("kind") == str(kind_binary)


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


def test_execute_uses_resolved_binary(
    kind_binary: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    check_output = MagicMock(return_value="ok")
    monkeypatch.setattr(shared.subprocess, "check_output", check_output)

    assert execute("kind", "version") == "ok"
    check_output.assert_called_once_with([str(kind_binary), "version"], text=True)
