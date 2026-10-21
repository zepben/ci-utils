from pathlib import Path

import yaml

from tests.support.execution import FakeExecuteFactory
from zep_dev.development_environments import cnpg, kubernetes
from zep_dev.development_environments.services import CnpgService
from zep_dev.development_environments.target import execution_target


def test_cnpg_commands_and_manifests_use_selected_target(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    applied = fake_execute(kubernetes).on("kubectl")
    service = CnpgService.model_validate(
        {
            "type": "cnpg",
            "namespace": "databases",
            "database": "eas",
            "owner": "eas",
            "password": "private",
            "spec": {"instances": 1},
        }
    )
    cnpg.apply_cnpg_service(target, "postgres", service)
    manifests = {
        document["kind"]: document
        for command in applied.calls
        if isinstance(content := command.kwargs.get("input"), str)
        for document in [yaml.safe_load(content)]
    }
    [wait] = [command for command in applied.calls if "wait" in command.args]

    assert set(manifests) == {"Secret", "Cluster"}
    assert manifests["Cluster"]["metadata"]["name"] == "postgres"
    assert all(
        document["metadata"]["namespace"] == "databases"
        for document in manifests.values()
    )
    assert "--namespace=databases" in wait.args
    for command in applied.calls:
        assert f"--kubeconfig={target.kubeconfig}" in command.args
        assert f"--context={target.context}" in command.args
