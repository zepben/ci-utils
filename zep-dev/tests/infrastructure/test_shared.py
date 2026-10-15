import subprocess
import sys
from pathlib import Path

import pytest

import zep_dev.shared as shared
from zep_dev.shared import (
    ResolvedChart,
    resolve,
    resolve_chart,
)


@pytest.fixture
def bin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "bin"
    d.mkdir()
    monkeypatch.setattr(shared, "get_bin_dir", lambda: d)
    monkeypatch.setenv("PATH", f"{d}:{tmp_path}")
    return d


def test_resolve_missing(bin_dir: Path) -> None:
    with pytest.raises(Exception, match="not installed"):
        resolve("kind")


def test_resolve_not_executable(bin_dir: Path) -> None:
    (bin_dir / "kind").write_text("data")
    with pytest.raises(Exception, match="not installed"):
        resolve("kind")


def test_resolve_unknown(bin_dir: Path) -> None:
    with pytest.raises(Exception, match="Failed to locate tool"):
        resolve("nosuch")


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


def test_execute_forwards_input_environment_and_captured_streams() -> None:
    result = shared.execute(
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
    assert result == shared.CommandResult(0, "selected\npayload\n", "diagnostic\n")


@pytest.mark.parametrize("check", [False, True], ids=["return-result", "raise-failure"])
def test_execute_preserves_failure_code_and_streams(check: bool) -> None:
    args = (
        sys.executable,
        "-c",
        "import sys; print('output'); print('error', file=sys.stderr); sys.exit(3)",
    )
    if check:
        with pytest.raises(subprocess.CalledProcessError) as failure:
            shared.execute(
                *args, capture_stdout=True, capture_stderr=True, skip_resolve=True
            )
        assert failure.value.returncode == 3
        assert failure.value.cmd == list(args)
        assert failure.value.stdout == "output\n"
        assert failure.value.stderr == "error\n"
    else:
        assert shared.execute(
            *args,
            capture_stdout=True,
            capture_stderr=True,
            skip_resolve=True,
            check=False,
        ) == shared.CommandResult(3, "output\n", "error\n")
