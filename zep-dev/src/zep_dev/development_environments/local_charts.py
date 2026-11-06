"""Package caller-owned working-tree charts into versioned local state."""

import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from zep_dev.chart_version import calculate_chart_version
from zep_dev.development_environments.distributions import ChartName
from zep_dev.development_environments.target import state_home
from zep_dev.errors import ZepDevError
from zep_dev.models import ChartMetadata
from zep_dev.shared import execute


@dataclass(frozen=True)
class LocalChartRef:
    name: ChartName
    version: str
    repo: Path
    package: Path
    source: Literal["local"] = "local"

    @property
    def chart(self) -> str:
        return str(self.package)

    def label(self) -> str:
        return f"{self.name}:{self.version}"


def resolve_local_chart(name: ChartName) -> LocalChartRef:
    repo = Path(
        execute(
            "git",
            "rev-parse",
            "--show-toplevel",
            skip_resolve=True,
            capture_stdout=True,
        ).stdout.strip()
    ).resolve()
    chart = repo / "helm" / "charts" / name
    metadata = ChartMetadata.from_chart_dir(chart)
    if metadata.name != name:
        raise ValueError(f"Expected chart {name} in caller's checkout at {chart}")
    version = calculate_chart_version(repo)
    package = (
        state_home() / "zep-dev" / "charts" / name / version / f"{name}-{version}.tgz"
    )
    return LocalChartRef(name=name, version=version, repo=repo, package=package)


def check_local_chart(ref: LocalChartRef) -> None:
    if not ref.package.is_file() or ref.package.stat().st_size == 0:
        raise ZepDevError(
            f"Missing local chart {ref.label()} at {ref.package}; "
            "run distribution build first from this checkout"
        )


def build_local_chart(
    ref: LocalChartRef, progress: Callable[[str], None] | None = None
) -> None:
    """Always rebuild; dirty edits share HEAD's version. Publish only on success."""
    if progress is not None:
        progress(f"  packaging local {ref.label()} from {ref.repo}")
    ref.package.parent.mkdir(parents=True, exist_ok=True)
    # Stage on the destination filesystem so the final replacement is atomic.
    with TemporaryDirectory(prefix=".build-", dir=ref.package.parent) as directory:
        staging = Path(directory)
        # Preserve sibling file:// dependencies and their uncommitted changes.
        charts = staging / "charts"
        shutil.copytree(ref.repo / "helm" / "charts", charts)
        chart = charts / ref.name
        execute("helm", "dependency", "build", str(chart))
        execute(
            "helm",
            "package",
            str(chart),
            "--version",
            ref.version,
            "--destination",
            str(staging),
        )
        archive = staging / ref.package.name
        if not archive.is_file() or archive.stat().st_size == 0:
            raise RuntimeError(f"Helm did not produce a chart package at {archive}")
        archive.replace(ref.package)
    if progress is not None:
        progress(f"  ready local {ref.label()} at {ref.package}")
