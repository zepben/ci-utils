from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from unittest.mock import call

from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute
from zep_dev.cli import cli
from zep_dev.commands.chart import push as push_module
from zep_dev.models import ChartTestingConfig


def test_push_adds_configured_repo_before_building_dependencies(
    helm_dir: Path,
    auth_json: Path,
    chart_testing_config: ChartTestingConfig,
    write_chart_testing_config: Callable[[ChartTestingConfig], None],
    fake_execute: Callable[[ModuleType], FakeExecute],
) -> None:
    repo_url = "https://grafana.github.io/helm-charts"
    chart_testing_config.chart_repos = [f"grafana={repo_url}"]
    write_chart_testing_config(chart_testing_config)
    chart = write_chart(
        helm_dir / "charts" / "alloy",
        {
            "name": "alloy",
            "version": "1.2.3",
            "dependencies": [
                {"name": "alloy", "version": "1.0.0", "repository": repo_url}
            ],
        },
    )
    fake = (
        fake_execute(push_module)
        .on(
            "helm",
            "show",
            "chart",
            returncode=1,
            stderr="manifest unknown",
            match_kwargs={"check": False},
        )
        .on("helm", "repo", "add")
        .on("helm", "dependency", "build")
        .on("helm", "package")
        .on("helm", "push")
    )

    result = CliRunner().invoke(
        cli,
        [
            "chart",
            "push",
            "--chart",
            str(chart),
            "--registry-config",
            str(auth_json),
            "--oci-repo",
            "org/repo",
        ],
    )

    assert result.exit_code == 0
    repo_call = call(
        "helm",
        "repo",
        "add",
        "grafana",
        repo_url,
        "--force-update",
        capture_stdout=True,
    )
    dependency_call = call(
        "helm",
        "dependency",
        "build",
        str(chart),
        "--registry-config",
        str(auth_json),
        capture_stdout=True,
    )
    assert fake.calls.index(repo_call) < fake.calls.index(dependency_call)


def test_push_is_idempotent_when_chart_present(
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
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr == "ewb:1.2.3 already exists in registry, skipping push\n"
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
