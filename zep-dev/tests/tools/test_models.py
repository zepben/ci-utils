import pytest

from zep_dev.models import ArchiveFormat, RequiredTool


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
