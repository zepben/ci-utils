"""One Kind Terraform root per Profile, calling native deployments wrappers.

Only module declarations and JSON input variables are generated. Kind fixture
policy lives alongside the production runtime-contract modules in deployments.
All runtime resources belong to the cluster; destroy discards state after Kind
has deleted it, without contacting Terraform providers.
"""

import json
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from zep_dev.k8s import KUBECONF_PATH
from zep_dev.models import DatabaseApp

if TYPE_CHECKING:
    from zep_dev.profile import Profile

GENERATED_TF_BASE: Final = Path("/tmp/zep-dev-terraform")
RUNTIME_DATABASE_MODULES: Final[dict[DatabaseApp, str]] = {
    "eas": "terraform/modules/kubernetes/eas-kind-runtime-contract",
    "hcs": "terraform/modules/kubernetes/hcs-kind-runtime-contract",
}


def profile_tf_dir(profile_name: str) -> Path:
    return GENERATED_TF_BASE / profile_name


def preflight_terraform(
    *, deployments_root: Path, databases: list[DatabaseApp]
) -> Path:
    root = deployments_root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"bindings.deployments_root not found: {root}")
    for app in databases:
        path = root / RUNTIME_DATABASE_MODULES[app]
        if not path.is_dir():
            raise FileNotFoundError(
                f"terraform database module not found for {app!r}: {path}"
            )
    return root


def generate_profile_terraform_root(
    profile: Profile, deployments_root: Path | None
) -> Path:
    root = profile_tf_dir(profile.metadata.name)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.chmod(0o700)
    modules: dict[str, Any] = {}
    databases: dict[str, Any] = {}
    for app, cnpg_name in profile.runtime.databases.items():
        if deployments_root is None:
            raise ValueError("deployments_root is required for runtime databases")
        module = (deployments_root / RUNTIME_DATABASE_MODULES[app]).resolve()
        source = os.path.relpath(module, start=root)
        # Local relative sources preserve sibling modules in the deployments tree.
        modules[f"{app}_runtime_contract"] = {
            "source": source if source.startswith(".") else f"./{source}",
            "namespace": "${var.namespace}",
            "database": f"${{var.databases.{app}}}",
        }
        cnpg = profile.cnpg(cnpg_name)
        databases[app] = {
            "host": f"{cnpg.name}-rw.{cnpg.namespace}.svc.cluster.local",
            "port": 5432,
            "name": cnpg.database,
            "username": cnpg.owner,
            "password": cnpg.password,
        }
    config = {
        "terraform": {
            "required_version": ">= 1.10.0",
            "required_providers": {
                "kubernetes": {"source": "hashicorp/kubernetes", "version": "~> 2.0"}
            },
        },
        "provider": {
            "kubernetes": {
                "config_path": "${var.kubeconfig}",
                "config_context": "${var.context}",
            }
        },
        "variable": {
            "namespace": {"type": "string"},
            "kubeconfig": {"type": "string"},
            "context": {"type": "string"},
            "databases": {
                "type": "map(object({host=string, port=number, name=string, username=string, password=string}))",
                "sensitive": True,
            },
        },
        "module": modules,
    }
    inputs = {
        "namespace": profile.namespace,
        "kubeconfig": str(KUBECONF_PATH),
        "context": f"kind-{profile.metadata.name}",
        "databases": databases,
    }
    (root / "main.tf.json").write_text(
        json.dumps(config, indent=2) + "\n", encoding="utf-8"
    )
    (root / "terraform.tfvars.json").write_text(
        json.dumps(inputs, indent=2) + "\n", encoding="utf-8"
    )
    return root


def discard_profile_terraform(profile_name: str) -> None:
    root = profile_tf_dir(profile_name)
    if root.exists():
        shutil.rmtree(root)
