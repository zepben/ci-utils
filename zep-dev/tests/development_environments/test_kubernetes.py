import subprocess
from pathlib import Path

import pytest

from tests.support.execution import FakeExecuteFactory
from zep_dev.development_environments import kubernetes
from zep_dev.development_environments.target import execution_target


def test_sensitive_kubectl_failure_hides_payload(
    tmp_path: Path, fake_execute: FakeExecuteFactory
) -> None:
    target = execution_target("integration", environ={"XDG_STATE_HOME": str(tmp_path)})
    calls = fake_execute(kubernetes).on(
        "kubectl", returncode=1, stderr="invalid secret TOKEN=private-value"
    )
    with pytest.raises(subprocess.CalledProcessError) as failure:
        kubernetes.kubectl(
            target, "apply", "-f", "-", input="TOKEN=private-value", sensitive=True
        )
    assert failure.value.cmd == ["kubectl", "<sensitive input>"]
    assert failure.value.stdout is None
    assert failure.value.stderr is None
    assert "private-value" not in str(failure.value)
    [apply] = calls.calls
    assert "private-value" not in repr(apply.args)
    assert apply.kwargs["input"] == "TOKEN=private-value"
