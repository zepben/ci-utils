import hashlib
import io
import os
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import Mock

import click
import pytest
import requests
from requests.exceptions import RequestException
from tenacity import wait_none

from zep_dev.commands.tools import commands as install_module
from zep_dev.commands.tools.commands import download, install_binary_tool
from zep_dev.models import ArchiveFormat, RequiredTool


@pytest.fixture
def no_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        install_module, "wait_exponential_jitter", lambda **_kwargs: wait_none()
    )


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
        sha256="0" * 64,
        archive_member="ct",
        archive_format=ArchiveFormat.TAR_GZ,
    )
    dest = install_binary_tool(tool, tools_dir)

    assert dest == tools_dir / "test-tool"
    assert dest.read_bytes() == b"#!/bin/sh\n"
    assert os.access(dest, os.X_OK)


def test_install_binary_tool_from_zip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tools_dir = tmp_path / "bin"
    tools_dir.mkdir()

    def fake_download(url: str, dest: Path, **kwargs: object) -> None:
        with zipfile.ZipFile(dest, "w") as archive:
            archive.writestr("terraform", b"#!/bin/sh\n")

    monkeypatch.setattr(install_module, "download", fake_download)

    tool = RequiredTool(
        name="test-tool",
        version="1.0.0",
        url="http://unused/{version}",
        sha256="0" * 64,
        archive_member="terraform",
        archive_format=ArchiveFormat.ZIP,
    )
    dest = install_binary_tool(tool, tools_dir)

    assert dest == tools_dir / "test-tool"
    assert dest.read_bytes() == b"#!/bin/sh\n"
    assert os.access(dest, os.X_OK)


def test_download_cleans_up_after_exhausted_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_retry_delay: None
) -> None:
    dest = tmp_path / "tool"

    def write_then_fail(
        url: str,
        dest: Path,
        *,
        expected_sha256: str,
        label: str | None = None,
    ) -> None:
        dest.write_bytes(b"partial")
        raise RequestException("fail")

    monkeypatch.setattr(install_module, "download_url", write_then_fail)
    with pytest.raises(RequestException):
        download("http://example/tool", dest, expected_sha256="0" * 64)
    assert not dest.exists()


@pytest.mark.parametrize("valid_checksum", [True, False], ids=["verified", "mismatch"])
def test_download_verifies_checksum_and_discards_untrusted_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, valid_checksum: bool
) -> None:
    payload = b"downloaded tool"
    response = requests.Response()
    response.status_code = 200
    response.headers["Content-Length"] = str(len(payload))
    response.raw = io.BytesIO(payload)
    request = Mock(return_value=response)
    monkeypatch.setattr(requests, "get", request)
    destination = tmp_path / "tool"
    checksum = hashlib.sha256(payload).hexdigest() if valid_checksum else "0" * 64
    if valid_checksum:
        install_module.download_url(
            "https://example.org/tool", destination, expected_sha256=checksum
        )
        assert destination.read_bytes() == payload
    else:
        with pytest.raises(click.ClickException, match="SHA256 mismatch"):
            install_module.download_url(
                "https://example.org/tool", destination, expected_sha256=checksum
            )
        assert not destination.exists()
    request.assert_called_once_with(
        "https://example.org/tool",
        stream=True,
        timeout=install_module.DOWNLOAD_TIMEOUT_SECONDS,
    )


@pytest.mark.parametrize(
    "change",
    [None, "version", "sha256"],
    ids=["unchanged", "new-version", "new-checksum"],
)
def test_install_skips_matching_tool_and_reinstalls_changed_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, change: str | None
) -> None:
    installed = RequiredTool(
        name="tool", version="1", url="https://example.org/{version}", sha256="0" * 64
    )
    hashes = tmp_path / "hashes"
    hashes.mkdir()
    installed.write_hash(hashes)
    selected = installed.model_copy(
        update={}
        if change is None
        else {change: "2" if change == "version" else "1" * 64}
    )
    install = Mock()
    monkeypatch.setattr(install_module, "TOOLS", [selected])
    monkeypatch.setattr(install_module, "get_bin_dir", lambda: tmp_path / "bin")
    monkeypatch.setattr(install_module, "get_hash_dir", lambda: hashes)
    monkeypatch.setattr(install_module, "install_binary_tool", install)

    install_module.install_binary_tools()

    if change is None:
        install.assert_not_called()
    else:
        install.assert_called_once_with(selected, tmp_path / "bin")
    assert selected.exists(hashes)
