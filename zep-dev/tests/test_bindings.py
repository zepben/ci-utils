"""Discovery and validation of developer-local Bindings."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from zep_dev.bindings import Bindings, load_bindings


def write_bindings(
    path: Path,
    *,
    deployments_root: str | None = None,
    mounts: dict[str, str] | None = None,
    **extra: object,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {**extra}
    if deployments_root is not None:
        data["deployments_root"] = deployments_root
    if mounts is not None:
        data["mounts"] = mounts
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_discovery_uses_first_existing_bindings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cwd = tmp_path / "work"
    cwd.mkdir()
    config = tmp_path / "config"
    explicit = write_bindings(
        tmp_path / "override.yaml", deployments_root="/override/deployments"
    )
    local = write_bindings(
        cwd / ".zep-dev" / "bindings.yaml", deployments_root="/local/deployments"
    )
    write_bindings(
        config / "zep-dev" / "bindings.yaml", deployments_root="/config/deployments"
    )
    monkeypatch.setenv("ZEP_DEV_BINDINGS", str(explicit))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))

    assert load_bindings(cwd).deployments_root == Path("/override/deployments")
    explicit.unlink()
    assert load_bindings(cwd).deployments_root == Path("/local/deployments")
    local.unlink()
    assert load_bindings(cwd).deployments_root == Path("/config/deployments")


def test_missing_bindings_lists_searched_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ZEP_DEV_BINDINGS", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    with pytest.raises(FileNotFoundError, match="Bindings not found") as error:
        load_bindings(tmp_path)
    assert str(tmp_path / ".zep-dev" / "bindings.yaml") in str(error.value)
    assert str(tmp_path / "config" / "zep-dev" / "bindings.yaml") in str(error.value)


def test_require_mount_and_deployments_root(tmp_path: Path) -> None:
    bindings = Bindings.from_path(
        write_bindings(
            tmp_path / "bindings.yaml",
            deployments_root="/deployments",
            mounts={"ewb-data": "/data"},
        )
    )
    assert bindings.require_deployments_root() == Path("/deployments")
    assert bindings.require_mount("ewb-data") == Path("/data")
    with pytest.raises(ValueError, match=r"slot 'missing'"):
        bindings.require_mount("missing")


def test_require_deployments_root_when_absent(tmp_path: Path) -> None:
    bindings = Bindings.from_path(
        write_bindings(tmp_path / "bindings.yaml", mounts={"ewb-data": "/data"})
    )
    with pytest.raises(ValueError, match="deployments_root is required"):
        bindings.require_deployments_root()


def test_bindings_forbids_extra_fields_and_relative_paths() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Bindings.model_validate({"other": True})
    with pytest.raises(ValidationError, match="absolute path"):
        Bindings.model_validate({"deployments_root": "relative/deployments"})
    with pytest.raises(ValidationError, match="absolute path"):
        Bindings.model_validate({"mounts": {"ewb-data": "relative/data"}})


def test_empty_bindings_file_loads(tmp_path: Path) -> None:
    path = tmp_path / "bindings.yaml"
    path.write_text("{}\n", encoding="utf-8")
    bindings = Bindings.from_path(path)
    assert bindings.deployments_root is None
    assert bindings.mounts == {}
