"""Generate stable Kind Terraform roots that call production runtime-contract modules.

Absolute module ``source`` values make Terraform copy the module as a package;
nested ``../`` siblings (e.g. kubernetes-service-account) then fail. Generated
roots therefore use a path relative to the root directory.

Templates live under ``zep_dev/resources/terraform/``. Module source and Kind
kubeconfig path are substituted at generation time.
"""

from __future__ import annotations

import logging
import os
from importlib.resources import files
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from zep_dev.k8s import KUBECONF_PATH
from zep_dev.models import ContractId

LOG = logging.getLogger(__name__)

GENERATED_TF_BASE: Final = Path("/tmp/zep-dev-terraform")

MODULE_SOURCE_PLACEHOLDER: Final = "__MODULE_SOURCE__"
KUBECONF_PATH_PLACEHOLDER: Final = "__KUBECONF_PATH__"

KNOWN_CONTRACTS: Final[dict[ContractId, str]] = {
    "hcs": "terraform/modules/kubernetes/hcs-runtime-contract",
    "eas": "terraform/modules/kubernetes/eas-runtime-contract",
}

_COMMON_TF_NAMES: Final = ("versions.tf", "providers.tf", "variables.tf")


class ProfileTerraformMeta(BaseModel):
    """Sidecar written beside generated roots so destroy needs only metadata.name."""

    model_config = ConfigDict(extra="forbid")

    namespace: str = Field(min_length=1)
    contracts: list[ContractId] = Field(min_length=1)


def profile_tf_dir(profile_name: str) -> Path:
    return GENERATED_TF_BASE / profile_name


def contract_root(profile_name: str, contract: ContractId) -> Path:
    return profile_tf_dir(profile_name) / contract


def resolve_deployments_root(deployments_root: Path) -> Path:
    if not deployments_root.is_absolute():
        raise ValueError(
            f"bindings.deployments_root must be an absolute path: {deployments_root}"
        )
    return deployments_root.resolve()


def module_path(deployments_root: Path, contract: ContractId) -> Path:
    return (deployments_root / KNOWN_CONTRACTS[contract]).resolve()


def preflight_terraform(
    *,
    deployments_root: Path,
    contracts: list[ContractId],
) -> Path:
    root = resolve_deployments_root(deployments_root)
    if not root.is_dir():
        raise FileNotFoundError(f"bindings.deployments_root not found: {root}")
    for contract in contracts:
        path = module_path(root, contract)
        if not path.is_dir():
            raise FileNotFoundError(
                f"terraform contract module not found for {contract!r}: {path}"
            )
    return root


def _module_source_relative(module_abs: Path, root: Path) -> str:
    rel = os.path.relpath(module_abs, start=root)
    return rel if rel.startswith(".") else f"./{rel}"


def _read_template(relative: str) -> str:
    resource = files("zep_dev.resources").joinpath(relative)
    return resource.read_text(encoding="utf-8")


def generate_contract_root(
    *,
    profile_name: str,
    contract: ContractId,
    deployments_root: Path,
) -> Path:
    module_abs = module_path(deployments_root, contract)
    root = contract_root(profile_name, contract)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    source = _module_source_relative(module_abs, root)
    for name in _COMMON_TF_NAMES:
        template = _read_template(f"terraform/common/{name}")
        if name == "providers.tf":
            if KUBECONF_PATH_PLACEHOLDER not in template:
                raise ValueError(
                    f"Terraform provider template missing {KUBECONF_PATH_PLACEHOLDER}"
                )
            template = template.replace(KUBECONF_PATH_PLACEHOLDER, str(KUBECONF_PATH))
        (root / name).write_text(template, encoding="utf-8")
    main = _read_template(f"terraform/{contract}/main.tf")
    if MODULE_SOURCE_PLACEHOLDER not in main:
        raise ValueError(
            f"terraform template for {contract!r} missing {MODULE_SOURCE_PLACEHOLDER}"
        )
    (root / "main.tf").write_text(
        main.replace(MODULE_SOURCE_PLACEHOLDER, source),
        encoding="utf-8",
    )
    return root


def write_profile_tf_meta(meta: ProfileTerraformMeta, profile_name: str) -> Path:
    base = profile_tf_dir(profile_name)
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    base.chmod(0o700)
    path = base / "meta.json"
    path.write_text(meta.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_profile_tf_meta(profile_name: str) -> ProfileTerraformMeta | None:
    path = profile_tf_dir(profile_name) / "meta.json"
    if not path.is_file():
        return None
    try:
        return ProfileTerraformMeta.model_validate_json(
            path.read_text(encoding="utf-8")
        )
    except OSError as exc:
        LOG.warning(
            "Could not read Terraform meta for profile %r at %s: %s; "
            "skipping terraform destroy",
            profile_name,
            path,
            exc,
        )
        return None
    except ValidationError as exc:
        LOG.warning(
            "Invalid Terraform meta for profile %r at %s (%s); "
            "skipping terraform destroy",
            profile_name,
            path,
            exc,
        )
        return None


def generate_profile_terraform_roots(
    *,
    profile_name: str,
    namespace: str,
    deployments_root: Path,
    contracts: list[ContractId],
) -> list[Path]:
    write_profile_tf_meta(
        ProfileTerraformMeta(namespace=namespace, contracts=contracts),
        profile_name,
    )
    return [
        generate_contract_root(
            profile_name=profile_name,
            contract=contract,
            deployments_root=deployments_root,
        )
        for contract in contracts
    ]
