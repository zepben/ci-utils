from pathlib import Path
from typing import Any

from tests.support.execution import FakeExecuteFactory, option_value
from zep_dev.development_environments import (
    kubernetes,
    manifests,
)
from zep_dev.development_environments.target import execution_target
from zep_dev.development_environments.templates import EnvironmentTemplate


def test_manifest_apply_targets_environment_namespace(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    source = tmp_path / "resources.yaml"
    source.write_text("apiVersion: v1\nkind: ConfigMap\nmetadata: {name: app}\n")
    calls = fake_execute(kubernetes).on("kubectl")
    manifests.apply_application_manifests(target, [source])
    [apply] = calls.calls
    assert "apply" in apply.args
    assert option_value(apply.args, "--namespace") == "integration"
    assert option_value(apply.args, "-f") == str(source)


def test_manifest_contents_are_left_for_kubectl(
    tmp_path: Path, basic_template: dict[str, Any]
) -> None:
    source = tmp_path / "resources.yaml"
    source.write_text("invalid: [yaml", encoding="utf-8")
    basic_template.update(
        distribution="distribution.yaml",
        applications={"eas": {"manifests": [source.name]}},
    )
    template = EnvironmentTemplate.model_validate(basic_template)

    assert manifests.resolve_application_manifests(
        tmp_path / "template.yaml", template
    ) == (source,)
    assert source.read_text(encoding="utf-8") == "invalid: [yaml"
