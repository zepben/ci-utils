import json
import subprocess
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner, Result

from tests.support.charts import pull_annotated_chart_package
from tests.support.execution import FakeExecute, FakeExecuteFactory
from zep_dev.charts import published
from zep_dev.cli import cli

pytestmark = pytest.mark.usefixtures("cli_environment")

ROOT = "terraform/deployments/customers/zepben-staging-aws/ewb-platform"
CONTRACT = {
    "zepben.com/runtime-contract-ref": "new",
    "org.opencontainers.image.source": "https://github.com/zepben/evolve-app-server",
}


def write_application(
    repo: Path, name: str, annotations: dict[str, str] | None = None
) -> Path:
    path = repo / "argo-cd-deployments/customer" / name / "application.yaml"
    path.parent.mkdir(parents=True)
    document = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": name, "annotations": annotations or {}},
        "spec": {
            "sources": [
                {
                    "repoURL": "ghcr.io/zepben/charts",
                    "chart": "eas",
                    "targetRevision": "2.0.0+abc",
                },
                {
                    "repoURL": "https://github.com/zepben/deployments.git",
                    "targetRevision": "HEAD",
                },
            ]
        },
    }
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


def pins(repo: Path) -> dict[str, object]:
    content: dict[str, object] = json.loads(
        (repo / ROOT / "runtime-contracts.tf.json").read_text(encoding="utf-8")
    )
    return content


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ROOT).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def staging(repo: Path) -> Path:
    return write_application(repo, "staging-eas", {"zepben.com/terraform-root": ROOT})


def pin_root(repo: Path, **locals_: str) -> None:
    (repo / ROOT / "runtime-contracts.tf.json").write_text(
        json.dumps({"locals": locals_}), encoding="utf-8"
    )


def publish(
    fake_execute: FakeExecuteFactory, annotations: dict[str, str]
) -> FakeExecute:
    return fake_execute(published).on(
        "helm", "pull", hook=pull_annotated_chart_package(annotations)
    )


def run_pin(*args: str | Path) -> Result:
    return CliRunner().invoke(
        cli, ["runtime-contract", "pin", *map(str, args)], catch_exceptions=False
    )


def test_pin_replaces_the_roots_outdated_pin_and_prints_how_to_apply_it(
    repo: Path, staging: Path, fake_execute: FakeExecuteFactory
) -> None:
    pin_root(repo, eas_runtime_contract_ref="old", hcs_runtime_contract_ref="hcs")
    publish(fake_execute, CONTRACT)

    result = run_pin(staging)

    assert result.exit_code == 0, result.output
    assert pins(repo) == {
        "locals": {"eas_runtime_contract_ref": "new", "hcs_runtime_contract_ref": "hcs"}
    }
    assert (
        "https://github.com/zepben/evolve-app-server/compare/old...new" in result.output
    )
    assert (
        "cd terraform && ./terraform.sh -d customers/zepben-staging-aws/ewb-platform apply"
        in result.output
    )


def test_pin_check_fails_without_changes_when_the_root_pins_another_contract(
    repo: Path, staging: Path, fake_execute: FakeExecuteFactory
) -> None:
    pin_root(repo, eas_runtime_contract_ref="old")
    publish(fake_execute, CONTRACT)

    result = run_pin("--check", staging)

    assert result.exit_code == 1
    assert "needs runtime contract new" in result.output
    assert pins(repo) == {"locals": {"eas_runtime_contract_ref": "old"}}


def test_pin_check_passes_when_the_root_pins_the_charts_contract(
    repo: Path, staging: Path, fake_execute: FakeExecuteFactory
) -> None:
    pin_root(repo, eas_runtime_contract_ref="new")
    publish(fake_execute, CONTRACT)

    assert run_pin("--check", staging).exit_code == 0


def test_chart_without_a_runtime_contract_needs_no_terraform_root(
    repo: Path, fake_execute: FakeExecuteFactory
) -> None:
    application = write_application(repo, "uncontracted")
    publish(fake_execute, {})

    result = run_pin("--check", application)

    assert result.exit_code == 0, result.output
    assert "no runtime contract" in result.output


def test_chart_with_a_runtime_contract_requires_a_terraform_root(
    repo: Path, fake_execute: FakeExecuteFactory
) -> None:
    application = write_application(repo, "unrooted")
    publish(fake_execute, CONTRACT)

    result = run_pin("--check", application)

    assert result.exit_code == 1
    assert "no zepben.com/terraform-root annotation" in result.output


def test_unpublished_chart_version_fails(
    staging: Path, fake_execute: FakeExecuteFactory
) -> None:
    fake_execute(published).on("helm", "pull", returncode=1, stderr="manifest unknown")

    result = run_pin("--check", staging)

    assert result.exit_code == 1
    assert "eas 2.0.0+abc: chart is not published" in result.output


def test_directory_selects_applications_that_name_a_terraform_root(
    repo: Path, staging: Path, fake_execute: FakeExecuteFactory
) -> None:
    write_application(repo, "unrooted")
    pin_root(repo, eas_runtime_contract_ref="new")
    pulls = publish(fake_execute, CONTRACT)

    result = run_pin("--check", repo / "argo-cd-deployments")

    assert result.exit_code == 0, result.output
    assert "unrooted" not in result.output
    assert len(pulls.calls) == 1
