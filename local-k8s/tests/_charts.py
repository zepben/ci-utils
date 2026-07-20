from pathlib import Path

import yaml


def write_chart(chart_dir: Path, chart_yaml: dict[str, object]) -> Path:
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "Chart.yaml").write_text(yaml.dump(chart_yaml))
    return chart_dir
