from pathlib import Path

import pytest

from local_k8s.models import RequiredTool


@pytest.fixture
def tool() -> RequiredTool:
    return RequiredTool(
        name="ct",
        version="1.0",
        url="http://example/{version}",
        archive_member="ct",
    )


def test_exists_when_hash_matches(tmp_path: Path, tool: RequiredTool) -> None:
    tool.write_hash(tmp_path)
    assert tool.exists(tmp_path) is True


def test_exists_when_hash_missing(tmp_path: Path, tool: RequiredTool) -> None:
    assert tool.exists(tmp_path) is False


def test_exists_when_hash_stale(tmp_path: Path, tool: RequiredTool) -> None:
    (tmp_path / tool.name).write_text("old-hash")
    assert tool.exists(tmp_path) is False
