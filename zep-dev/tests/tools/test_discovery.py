import sys
from pathlib import Path

import pytest

from zep_dev.errors import ZepDevError
from zep_dev.infrastructure import tools


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setattr(tools, "get_bin_dir", lambda: d)
    monkeypatch.setenv("PATH", f"{d}:{tmp_path}")
    return d


def test_resolve_missing(bin_dir: Path) -> None:
    with pytest.raises(ZepDevError, match="not installed"):
        tools.resolve("kind")


def test_resolve_not_executable(bin_dir: Path) -> None:
    (bin_dir / "kind").write_text("data")
    with pytest.raises(ZepDevError, match="not installed"):
        tools.resolve("kind")


def test_resolve_unknown(bin_dir: Path) -> None:
    with pytest.raises(Exception, match="Failed to locate tool"):
        tools.resolve("nosuch")


def test_tool_paths_follow_the_application_virtualenv_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(sys, "prefix", str(tmp_path / "application" / ".venv"))
    monkeypatch.setattr(sys, "base_prefix", str(tmp_path / "python"))

    assert tools.get_repo_name() == "application"
    assert tools.get_tools_dir() == home / ".local/share/application"
    assert tools.get_bin_dir() == home / ".local/share/application/bin"
    assert tools.get_hash_dir() == home / ".local/share/application/hash"


def test_tool_paths_refuse_execution_outside_a_virtualenv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "prefix", sys.base_prefix)

    with pytest.raises(ZepDevError, match="application virtualenv"):
        tools.get_tools_dir()
