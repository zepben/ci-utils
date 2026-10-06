import json
from pathlib import Path

import pytest

from zep_dev import terraform_roots
from zep_dev.commands.terraform import commands as terraform_commands
from zep_dev.k8s import KUBECONF_PATH
from zep_dev.profile import Profile
from zep_dev.terraform_roots import (
    discard_profile_terraform,
    generate_profile_terraform_root,
    preflight_terraform,
    profile_tf_dir,
)


@pytest.fixture
def deployments_root(tmp_path: Path) -> Path:
    return tmp_path / 'deployments with "quotes" and ${literal}'


@pytest.fixture
def terraform_root(
    contract_profile: Profile, generated_tf_base: Path, deployments_root: Path
) -> Path:
    return generate_profile_terraform_root(contract_profile, deployments_root)


def test_preflight_rejects_missing_module(tmp_path: Path) -> None:
    root = tmp_path / "deployments"
    root.mkdir()
    with pytest.raises(FileNotFoundError, match="eas-kind-runtime-contract"):
        preflight_terraform(deployments_root=root, databases=["eas"])


def test_generated_root_wires_databases_to_kind(
    terraform_root: Path, deployments_root: Path
) -> None:
    config = json.loads((terraform_root / "main.tf.json").read_text())
    inputs = json.loads((terraform_root / "terraform.tfvars.json").read_text())

    assert terraform_root == profile_tf_dir("demo")
    assert set(config["module"]) == {"eas_runtime_contract", "hcs_runtime_contract"}
    assert inputs["databases"]["hcs"]["host"] == (
        "hcs-kind-pg-rw.integration.svc.cluster.local"
    )
    assert inputs["namespace"] == "integration"
    assert inputs["kubeconfig"] == str(KUBECONF_PATH)
    assert inputs["context"] == "kind-demo"
    assert config["provider"]["kubernetes"] == {
        "config_path": "${var.kubeconfig}",
        "config_context": "${var.context}",
    }
    for app in ("eas", "hcs"):
        module = config["module"][f"{app}_runtime_contract"]
        assert module["namespace"] == "${var.namespace}"
        assert module["database"] == f"${{var.databases.{app}}}"
        assert (terraform_root / module["source"]).resolve() == (
            deployments_root / terraform_roots.RUNTIME_DATABASE_MODULES[app]
        )


def test_generated_inputs_keep_credentials_private_and_literal(
    contract_profile: Profile, generated_tf_base: Path, deployments_root: Path
) -> None:
    password = 'quote"slash\\newline\n${expression}%{directive}&=+'
    for name in contract_profile.runtime.databases.values():
        contract_profile.cnpg(name).password = password

    root = generate_profile_terraform_root(contract_profile, deployments_root)
    config = json.loads((root / "main.tf.json").read_text())
    inputs = json.loads((root / "terraform.tfvars.json").read_text())

    assert {db["password"] for db in inputs["databases"].values()} == {password}
    assert json.dumps(password) not in (root / "main.tf.json").read_text()
    assert config["variable"]["databases"]["sensitive"] is True
    assert root.stat().st_mode & 0o777 == 0o700


def test_regeneration_preserves_state_when_database_removed(
    contract_profile: Profile, terraform_root: Path, deployments_root: Path
) -> None:
    state = terraform_root / "terraform.tfstate"
    state.write_text("preserve")
    contract_profile.runtime.databases.pop("hcs")

    regenerated = generate_profile_terraform_root(contract_profile, deployments_root)

    assert regenerated == terraform_root
    assert state.read_text() == "preserve"
    config = json.loads((regenerated / "main.tf.json").read_text())
    assert set(config["module"]) == {"eas_runtime_contract"}


def test_discard_removes_only_profile_files_and_state(
    tmp_path: Path, generated_tf_base: Path, state_root: Path
) -> None:
    root = profile_tf_dir("demo")
    root.mkdir(parents=True)
    (root / "terraform.tfstate").write_text("{}")
    (root / "terraform.tfvars.json").write_text("{}")
    unrelated = profile_tf_dir("another")
    unrelated.mkdir()
    (unrelated / "terraform.tfstate").write_text("{}")
    standalone = terraform_commands.terraform_state_path(
        tmp_path / "standalone", "platform"
    )
    standalone.parent.mkdir(parents=True)
    standalone.write_text("{}")

    discard_profile_terraform("demo")
    discard_profile_terraform("demo")

    assert not root.exists()
    assert (unrelated / "terraform.tfstate").is_file()
    assert standalone.is_file()
