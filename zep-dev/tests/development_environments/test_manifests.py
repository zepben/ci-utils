from pathlib import Path

from tests.support.execution import FakeExecuteFactory, option_value
from zep_dev.development_environments import (
    kubernetes,
    manifests,
)
from zep_dev.development_environments.target import execution_target


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
