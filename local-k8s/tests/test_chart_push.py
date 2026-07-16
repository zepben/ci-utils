from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute
from local_k8s.cli import cli
from local_k8s.commands.chart import push as push_module


def test_push_fail_if_exists_aborts_when_chart_present(
    tmp_path: Path, fake_execute: Callable[[ModuleType], FakeExecute]
) -> None:
    chart = write_chart(
        tmp_path / "charts" / "ewb", {"name": "ewb", "version": "1.2.3"}
    )

    auth = tmp_path / "auth.json"
    auth.write_text("{}\n")

    fake = fake_execute(push_module)
    fake.on("helm", "show", "chart")

    result = CliRunner().invoke(
        cli,
        [
            "chart",
            "push",
            "--chart",
            str(chart),
            "--registry-config",
            str(auth),
            "--oci-repo",
            "org/repo",
            "--fail-if-exists",
        ],
    )

    assert result.exit_code != 0
    assert "already exists" in result.output
    assert fake.calls == [
        call(
            "helm",
            "show",
            "chart",
            "oci://ghcr.io/org/repo/ewb",
            "--version",
            "1.2.3",
            "--registry-config",
            str(auth),
            check=False,
            capture_stdout=True,
            capture_stderr=True,
        ),
    ]
