import json
from pathlib import Path

from click.testing import CliRunner

from _charts import write_chart
from local_k8s.cli import cli


def test_metadata_full_fields(tmp_path: Path) -> None:
    chart_yaml = {
        "name": "mychart",
        "version": "1.2.3",
        "type": "library",
        "appVersion": "9.0",
        "dependencies": [],
    }
    chart_dir = write_chart(tmp_path / "mychart", chart_yaml)

    result = CliRunner().invoke(cli, ["chart", "metadata", "--chart", str(chart_dir)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == chart_yaml


def test_metadata_missing_version_fails(tmp_path: Path) -> None:
    chart_dir = write_chart(tmp_path / "mychart", {"name": "mychart"})

    result = CliRunner().invoke(cli, ["chart", "metadata", "--chart", str(chart_dir)])

    assert result.exit_code != 0
