import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from local_k8s.cli import cli


def _write_chart(tmp_path: Path, chart_yaml: dict[str, object]) -> Path:
    chart_dir = tmp_path / "mychart"
    chart_dir.mkdir()
    (chart_dir / "Chart.yaml").write_text(yaml.dump(chart_yaml))
    return chart_dir


def test_metadata_full_fields(tmp_path: Path) -> None:
    chart_yaml = {
        "name": "mychart",
        "version": "1.2.3",
        "type": "library",
        "appVersion": "9.0",
    }
    chart_dir = _write_chart(
        tmp_path,
        chart_yaml,
    )

    result = CliRunner().invoke(cli, ["chart", "metadata", "--chart", str(chart_dir)])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == chart_yaml


def test_metadata_missing_version_fails(tmp_path: Path) -> None:
    chart_dir = _write_chart(tmp_path, {"name": "mychart"})

    result = CliRunner().invoke(cli, ["chart", "metadata", "--chart", str(chart_dir)])

    assert result.exit_code != 0
