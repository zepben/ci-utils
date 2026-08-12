import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from _charts import write_chart
from zep_dev.cli import cli


def test_list_selects_annotated_application_charts_in_path_order(
    helm_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    charts_dir = helm_dir / "charts"
    annotation = {"zepben.com/publish-with-application-image": "true"}
    write_chart(
        charts_dir / "zebra",
        {
            "name": "zebra",
            "version": "1.0.0",
            "annotations": annotation,
        },
    )
    write_chart(
        charts_dir / "alpha",
        {
            "name": "alpha",
            "version": "1.0.0",
            "annotations": annotation,
        },
    )
    write_chart(
        charts_dir / "unannotated",
        {"name": "unannotated", "version": "1.0.0"},
    )
    write_chart(
        charts_dir / "library",
        {
            "name": "library",
            "version": "1.0.0",
            "type": "library",
            "annotations": annotation,
        },
    )
    write_chart(
        charts_dir / "parent" / "nested",
        {
            "name": "nested",
            "version": "1.0.0",
            "annotations": annotation,
        },
    )
    monkeypatch.chdir(helm_dir.parent)

    result = CliRunner().invoke(
        cli,
        [
            "chart",
            "list",
            "--helm-dir",
            "helm",
            "--annotation",
            "zepben.com/publish-with-application-image=true",
            "--type",
            "application",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == [
        "helm/charts/alpha",
        "helm/charts/zebra",
    ]
    assert result.stderr == ""


def test_list_rejects_invalid_annotation(helm_dir: Path) -> None:
    result = CliRunner().invoke(
        cli,
        [
            "chart",
            "list",
            "--helm-dir",
            str(helm_dir),
            "--annotation",
            "invalid",
        ],
    )

    assert result.exit_code != 0
    assert "--annotation" in result.stderr
