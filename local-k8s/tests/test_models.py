from pathlib import Path

import pytest

from local_k8s.models import CiSecret, RequiredTool


@pytest.fixture
def tool() -> RequiredTool:
    return RequiredTool(
        name="ct",
        version="1.0",
        url="http://example/{version}",
        archive_member="ct",
    )


def test_ci_secret_resolve_path_missing_env_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = CiSecret(name="aws-creds", kind="env-file", env_var="AWS_CREDS_FILE")
    monkeypatch.delenv("AWS_CREDS_FILE", raising=False)

    with pytest.raises(ValueError, match="AWS_CREDS_FILE is not set"):
        secret.resolve_path()


def test_exists_when_hash_matches(tmp_path: Path, tool: RequiredTool) -> None:
    tool.write_hash(tmp_path)
    assert tool.exists(tmp_path) is True


def test_exists_when_hash_missing(tmp_path: Path, tool: RequiredTool) -> None:
    assert tool.exists(tmp_path) is False


def test_exists_when_hash_stale(tmp_path: Path, tool: RequiredTool) -> None:
    (tmp_path / tool.name).write_text("old-hash")
    assert tool.exists(tmp_path) is False
