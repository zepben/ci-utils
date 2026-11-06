from pathlib import Path

import pytest

from tests.support.execution import FakeExecuteFactory, option_value
from zep_dev.development_environments import kubernetes, supporting
from zep_dev.development_environments.services import HelmService, RawService
from zep_dev.development_environments.target import execution_target


def test_raw_service_applies_all_urls_then_waits(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:

    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    calls = fake_execute(kubernetes).on("kubectl")
    service = RawService.model_validate(
        {
            "type": "raw",
            "manifests": ["https://example.org/one", "https://example.org/two"],
            "wait_timeout": "90s",
        }
    )
    supporting.apply_raw_service(target, service)
    applied = [entry for entry in calls.calls if "apply" in entry.args]
    [wait] = [entry for entry in calls.calls if "wait" in entry.args]

    assert (
        sorted(option_value(entry.args, "-f") for entry in applied) == service.manifests
    )
    assert all("--server-side" in entry.args for entry in applied)
    assert option_value(wait.args, "--for") == "condition=Established"
    assert "customresourcedefinitions" in wait.args
    assert "--all" in wait.args
    assert option_value(wait.args, "--timeout") == "90s"
    assert all(calls.calls.index(entry) < calls.calls.index(wait) for entry in applied)


def test_invalid_secret_response_stops_before_generating_credentials(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:

    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    service = HelmService.model_validate(
        {
            "type": "helm",
            "chart": "helper",
            "repository": "https://example.org/charts",
            "version": "1",
            "load_db_credentials": {"from_secret": "database", "database": "app"},
        }
    )
    calls = fake_execute(kubernetes).on("kubectl", stdout='{"data": {"password": 123}}')
    with pytest.raises(ValueError, match="invalid Secret data"):
        supporting.apply_load_db_credentials(target, service)
    assert all("apply" not in call.args for call in calls.calls)
