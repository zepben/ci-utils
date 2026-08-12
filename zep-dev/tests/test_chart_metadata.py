import json
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from _charts import write_chart
from zep_dev.cli import cli
from zep_dev.commands.chart import metadata as metadata_module


def test_metadata_full_fields(tmp_path: Path) -> None:
    chart_yaml: dict[str, object] = {
        "name": "mychart",
        "version": "1.2.3",
        "type": "library",
        "appVersion": "9.0",
        "dependencies": [],
    }
    chart_dir = write_chart(tmp_path / "mychart", chart_yaml)

    result = CliRunner().invoke(
        cli, ["chart", "metadata", "show", "--chart", str(chart_dir)]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == chart_yaml


def test_metadata_missing_version_fails(tmp_path: Path) -> None:
    chart_dir = write_chart(tmp_path / "mychart", {"name": "mychart"})

    result = CliRunner().invoke(
        cli, ["chart", "metadata", "show", "--chart", str(chart_dir)]
    )

    assert result.exit_code != 0


def test_metadata_update_sets_release_and_image_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    chart_dir = write_chart(
        tmp_path / "mychart",
        {"apiVersion": "v2", "name": "mychart", "version": "0.0.0"},
    )
    (chart_dir / "values.yaml").write_text("replicas: 2\n", encoding="utf-8")
    monkeypatch.setattr(
        metadata_module, "calculate_chart_version", lambda: "1.2.3-4+abc1234"
    )

    result = CliRunner().invoke(
        cli,
        [
            "chart",
            "metadata",
            "update",
            "--chart",
            str(chart_dir),
            "--image-tag",
            "sha-abc1234",
        ],
    )

    assert result.exit_code == 0
    chart_yaml = yaml.safe_load((chart_dir / "Chart.yaml").read_text())
    values_yaml = yaml.safe_load((chart_dir / "values.yaml").read_text())
    assert chart_yaml["version"] == "1.2.3-4+abc1234"
    assert chart_yaml["appVersion"] == "1.2.3-4+abc1234"
    assert values_yaml == {"replicas": 2, "image": {"tag": "sha-abc1234"}}


def test_metadata_update_without_image_tag_leaves_values_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart_dir = write_chart(
        tmp_path / "mychart", {"name": "mychart", "version": "0.0.0"}
    )
    values_yaml = chart_dir / "values.yaml"
    values_yaml.write_text("unchanged: true\n", encoding="utf-8")
    monkeypatch.setattr(metadata_module, "calculate_chart_version", lambda: "2.0.0")

    result = CliRunner().invoke(
        cli, ["chart", "metadata", "update", "--chart", str(chart_dir)]
    )

    assert result.exit_code == 0
    assert values_yaml.read_text(encoding="utf-8") == "unchanged: true\n"
