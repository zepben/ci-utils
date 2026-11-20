import subprocess
import sys
from pathlib import Path

import pytest

from zep_dev.errors import ZepDevError
from zep_dev.infrastructure import execution, tools


def test_execute_forwards_input_environment_and_captured_streams() -> None:
    result = execution.execute(
        sys.executable,
        "-c",
        "import os, sys; print(os.environ['ZEP_TEST']); print(sys.stdin.read()); print('diagnostic', file=sys.stderr)",
        input="payload",
        env={"ZEP_TEST": "selected"},
        capture_stdout=True,
        capture_stderr=True,
        skip_resolve=True,
        timeout=10,
    )
    assert result == execution.CommandResult(0, "selected\npayload\n", "diagnostic\n")


@pytest.mark.parametrize("check", [False, True], ids=["return-result", "raise-failure"])
def test_execute_preserves_failure_code_and_streams(check: bool) -> None:
    args = (
        sys.executable,
        "-c",
        "import sys; print('output'); print('error', file=sys.stderr); sys.exit(3)",
    )
    if check:
        with pytest.raises(subprocess.CalledProcessError) as failure:
            execution.execute(
                *args, capture_stdout=True, capture_stderr=True, skip_resolve=True
            )
        assert failure.value.returncode == 3
        assert failure.value.cmd == list(args)
        assert failure.value.stdout == "output\n"
        assert failure.value.stderr == "error\n"
    else:
        assert execution.execute(
            *args,
            capture_stdout=True,
            capture_stderr=True,
            skip_resolve=True,
            check=False,
        ) == execution.CommandResult(3, "output\n", "error\n")


def test_execute_checks_managed_tool_availability_before_starting_a_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tools, "get_bin_dir", lambda: tmp_path / "missing-bin")

    def unexpected_process(*args: object, **kwargs: object) -> None:
        pytest.fail("a missing managed tool must be refused before process creation")

    monkeypatch.setattr(subprocess, "run", unexpected_process)
    with pytest.raises(ZepDevError, match="kind not installed"):
        execution.execute("kind", "get", "clusters")
