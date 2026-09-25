"""Credential preflight for source builds that need to dispatch."""

import json
from pathlib import Path

import pytest

from zep_dev.oci import require_ghcr_credentials


def test_helm_config_ghcr_entry_allows_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"auths": {"ghcr.io": {"auth": "opaque"}}}))
    monkeypatch.setenv("HELM_REGISTRY_CONFIG", str(path))
    require_ghcr_credentials()


def test_missing_ghcr_entry_fails_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"auths": {}}))
    monkeypatch.setenv("HELM_REGISTRY_CONFIG", str(path))
    with pytest.raises(FileNotFoundError, match="GHCR credentials missing"):
        require_ghcr_credentials()
