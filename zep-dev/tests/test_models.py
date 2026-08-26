from pathlib import Path

import pytest

from zep_dev.models import ArchiveFormat, CiSecret, RequiredTool


@pytest.fixture
def tool() -> RequiredTool:
    return RequiredTool(
        name="ct",
        version="1.0",
        url="http://example/{version}",
        sha256="0" * 64,
        archive_member="ct",
        archive_format=ArchiveFormat.TAR_GZ,
    )


@pytest.mark.parametrize(
    ("archive_member", "archive_format"),
    [
        ("tool", ArchiveFormat.NONE),
        (None, ArchiveFormat.TAR_GZ),
        (None, ArchiveFormat.ZIP),
    ],
)
def test_required_tool_rejects_inconsistent_archive_configuration(
    archive_member: str | None,
    archive_format: ArchiveFormat,
) -> None:
    with pytest.raises(
        ValueError,
        match="archive_member and archive_format must be set together",
    ):
        RequiredTool(
            name="test-tool",
            version="1.0.0",
            url="http://unused/{version}",
            sha256="0" * 64,
            archive_member=archive_member,
            archive_format=archive_format,
        )


def test_ci_secret_resolve_value_missing_env_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = CiSecret(name="aws-creds", env_var="AWS_ACCESS_KEY_ID")
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)

    with pytest.raises(ValueError, match="AWS_ACCESS_KEY_ID is not set"):
        secret.resolve_value()


def test_ci_secret_resolve_value_reads_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = CiSecret(name="aws-creds", env_var="AWS_ACCESS_KEY_ID")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-access-key")

    assert secret.resolve_value() == "test-access-key"


def test_exists_when_hash_matches(tmp_path: Path, tool: RequiredTool) -> None:
    tool.write_hash(tmp_path)
    assert tool.exists(tmp_path) is True


def test_exists_when_hash_missing(tmp_path: Path, tool: RequiredTool) -> None:
    assert tool.exists(tmp_path) is False


def test_exists_when_hash_stale(tmp_path: Path, tool: RequiredTool) -> None:
    (tmp_path / tool.name).write_text("old-hash")
    assert tool.exists(tmp_path) is False
