import io
import os
import tarfile
from pathlib import Path

import pytest
from requests.exceptions import RequestException

from local_k8s.commands.tools import commands as install_module
from local_k8s.commands.tools.commands import download, install_binary_tool
from local_k8s.models import RequiredTool


@pytest.fixture(autouse=True)
def _no_download_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _: None)


def test_install_binary_tool_from_archive(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools_dir = tmp_path / "bin"
    tools_dir.mkdir()

    def fake_download(url: str, dest: Path, **kwargs: object) -> None:
        data = b"#!/bin/sh\n"
        with tarfile.open(dest, "w:gz") as tar:
            info = tarfile.TarInfo(name="ct")
            info.size = len(data)
            info.mode = 0o755
            tar.addfile(info, io.BytesIO(data))

    monkeypatch.setattr(install_module, "download", fake_download)

    tool = RequiredTool(
        name="test-tool",
        version="3.14.0",
        url="http://unused/{version}",
        archive_member="ct",
    )
    dest = install_binary_tool(tool, tools_dir)

    assert dest == tools_dir / "test-tool"
    assert dest.read_bytes() == b"#!/bin/sh\n"
    assert os.access(dest, os.X_OK)


def test_download_cleans_up_after_exhausted_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "tool"

    def write_then_fail(url: str, dest: Path, *, label: str | None = None) -> None:
        dest.write_bytes(b"partial")
        raise RequestException("fail")

    monkeypatch.setattr(install_module, "download_url", write_then_fail)
    with pytest.raises(RequestException):
        download("http://example/tool", dest)
    assert not dest.exists()
