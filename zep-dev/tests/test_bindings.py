from pathlib import Path

import pytest
from pydantic import ValidationError

from zep_dev.bindings import Bindings, load_bindings


def test_discovery_uses_first_existing_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ZEP_DEV_BINDINGS", raising=False)
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    local = tmp_path / ".zep-dev"
    local.mkdir()
    (local / "bindings.yaml").write_text(
        "mounts:\n  ewb-data: /tmp/from-local\n", encoding="utf-8"
    )
    xdg = config_home / "zep-dev"
    xdg.mkdir(parents=True)
    (xdg / "bindings.yaml").write_text(
        "mounts:\n  ewb-data: /tmp/from-xdg\n", encoding="utf-8"
    )

    loaded = load_bindings()
    assert loaded.mounts["ewb-data"] == Path("/tmp/from-local")


def test_bindings_require_absolute_paths() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        Bindings.model_validate({"deployments_root": "relative/path"})
    with pytest.raises(ValidationError, match="absolute"):
        Bindings.model_validate({"mounts": {"ewb-data": "relative"}})
