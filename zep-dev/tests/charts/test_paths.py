from pathlib import Path

import pytest

from zep_dev.charts.utils import ResolvedChart, resolve_chart


def test_resolve_chart_accepts_repo_root_relative_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    helm_dir = (tmp_path / "helm").resolve()
    chart_dir = helm_dir / "charts" / "myapp"
    chart_dir.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    result = resolve_chart(helm_dir, Path("helm/charts/myapp"))

    assert result == ResolvedChart(
        absolute_path=chart_dir,
        path_relative_to_helm_dir=Path("charts/myapp"),
    )


def test_resolve_chart_outside_helm_dir_raises(tmp_path: Path) -> None:
    helm_dir = (tmp_path / "helm").resolve()
    helm_dir.mkdir()
    outside_chart = (tmp_path / "other" / "myapp").resolve()

    with pytest.raises(ValueError) as caught:
        resolve_chart(helm_dir, outside_chart)

    assert caught.value.__cause__ is None
    assert str(outside_chart) in str(caught.value)
    assert caught.value.__notes__ == [
        f"--chart {outside_chart} is not inside --helm-dir {helm_dir}"
    ]
