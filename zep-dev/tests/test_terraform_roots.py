"""Tests for Kind Terraform root generation."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pydantic import ValidationError

from zep_dev.distribution import TerraformSettings
from zep_dev.k8s import KUBECONF_PATH
from zep_dev.terraform_roots import (
    MODULE_SOURCE_PLACEHOLDER,
    generate_contract_root,
    generate_profile_terraform_roots,
    module_path,
    preflight_terraform,
    profile_tf_dir,
    read_profile_tf_meta,
)


@pytest.fixture
def generated_tf_base(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    base = tmp_path / "generated"
    monkeypatch.setattr("zep_dev.terraform_roots.GENERATED_TF_BASE", base)
    return base


def _deployments_with_contracts(tmp_path: Path, *names: str) -> Path:
    deployments = tmp_path / "deployments"
    for name in names:
        (deployments / "terraform/modules/kubernetes" / name).mkdir(parents=True)
    return deployments


def _module_source_from_main(main: str) -> str:
    source_line = next(line for line in main.splitlines() if "source =" in line)
    # source = "...."
    return source_line.split("=", 1)[1].strip().strip('"')


def test_generate_hcs_root_uses_relative_module_source(
    tmp_path: Path, generated_tf_base: Path
) -> None:
    deployments = _deployments_with_contracts(tmp_path, "hcs-runtime-contract")

    root = generate_contract_root(
        profile_name="platform",
        contract="hcs",
        deployments_root=deployments,
    )

    main = (root / "main.tf").read_text(encoding="utf-8")
    assert MODULE_SOURCE_PLACEHOLDER not in main
    source = _module_source_from_main(main)
    assert (root / source).resolve() == module_path(deployments, "hcs")
    assert "namespace                       = var.namespace" in main
    assert "hcs-kind-pg-rw.${var.namespace}.svc.cluster.local" in main
    provider = (root / "providers.tf").read_text(encoding="utf-8")
    assert f'config_path = "{KUBECONF_PATH}"' in provider
    assert "__KUBECONF_PATH__" not in provider
    assert (root / "variables.tf").is_file()
    assert (root / "versions.tf").is_file()


def test_generate_eas_root_sources_prod_module(
    tmp_path: Path, generated_tf_base: Path
) -> None:
    deployments = _deployments_with_contracts(tmp_path, "eas-runtime-contract")

    root = generate_contract_root(
        profile_name="platform",
        contract="eas",
        deployments_root=deployments,
    )
    main = (root / "main.tf").read_text(encoding="utf-8")
    source = _module_source_from_main(main)
    assert (root / source).resolve() == module_path(deployments, "eas")
    assert "eas-kind-pg-rw.${var.namespace}.svc.cluster.local" in main


def test_preflight_rejects_missing_module(tmp_path: Path) -> None:
    deployments = tmp_path / "deployments"
    deployments.mkdir()
    with pytest.raises(FileNotFoundError, match="contract module not found"):
        preflight_terraform(
            deployments_root=deployments,
            contracts=["eas"],
        )


def test_terraform_settings_rejects_unknown_contract() -> None:
    with pytest.raises(ValidationError, match="contracts"):
        TerraformSettings.model_validate({"contracts": ["nope"]})


def test_terraform_settings_rejects_deployments_root() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        TerraformSettings.model_validate(
            {"deployments_root": "/tmp/deployments", "contracts": ["eas"]}
        )


def test_generate_profile_writes_meta(tmp_path: Path, generated_tf_base: Path) -> None:
    deployments = _deployments_with_contracts(
        tmp_path, "hcs-runtime-contract", "eas-runtime-contract"
    )

    roots = generate_profile_terraform_roots(
        profile_name="platform",
        namespace="platform",
        deployments_root=deployments,
        contracts=["eas", "hcs"],
    )
    assert len(roots) == 2
    meta = read_profile_tf_meta("platform")
    assert meta is not None
    assert meta.namespace == "platform"
    assert meta.contracts == ["eas", "hcs"]


def test_read_profile_tf_meta_warns_on_corrupt_json(
    generated_tf_base: Path, caplog: pytest.LogCaptureFixture
) -> None:
    meta_path = profile_tf_dir("broken") / "meta.json"
    meta_path.parent.mkdir(parents=True)
    meta_path.write_text("{not-json\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING, logger="zep_dev.terraform_roots"):
        assert read_profile_tf_meta("broken") is None

    assert "Invalid Terraform meta" in caplog.text
    assert "skipping terraform destroy" in caplog.text
