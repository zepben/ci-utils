"""Package caller-owned working-tree charts, and their application images, into local state."""

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
from zep_dev.infrastructure.container_engine import (
    build_image,
    choose_engine,
    save_image_archive,
    tag_image,
)
from zep_dev.models import ChartMetadata, ChartValues
from zep_dev.shared import execute


@dataclass(frozen=True)
class LocalChartRef:
    name: ChartName
    version: str
    repo: Path
    package: Path
    # The image repository, when the chart is published with the application image.
    image: str | None = None
    source: Literal["local"] = "local"

    @property
    def chart(self) -> str:
        return str(self.package)

    @property
    def image_archive(self) -> Path:
        """One archive per chart, replaced together with its package."""
        return self.package.parent.parent / f"{self.name}.tar"

    def label(self) -> str:
        return f"{self.name}:{self.version}"


def resolve_local_chart(name: ChartName, image_repository: str) -> LocalChartRef:
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
    image = image_repository if metadata.publishes_application_image else None
    return LocalChartRef(
        name=name, version=version, repo=repo, package=package, image=image
    )


def check_local_chart(ref: LocalChartRef) -> None:
    if not ref.package.is_file() or ref.package.stat().st_size == 0:
        raise ZepDevError(
            f"Missing local chart {ref.label()} at {ref.package}; "
            "run distribution build first from this checkout"
        )
    if ref.image is not None and (
        not ref.image_archive.is_file() or ref.image_archive.stat().st_size == 0
    ):
        raise ZepDevError(
            f"Missing local image for {ref.label()} at {ref.image_archive}; "
            "run distribution build first from this checkout"
        )


def build_secrets() -> dict[str, Path]:
    """The build secrets release passes (zepben/.github build-sealed-docker-image.yml)."""
    home = Path.home()
    secrets = {
        "npm": home / ".npmrc",
        "maven": home / ".m2" / "settings.xml",
        "nuget": home / ".nuget" / "NuGet" / "NuGet.Config",
    }
    return {name: path for name, path in secrets.items() if path.is_file()}


def build_local_image(repo: Path, image: str, archive: Path) -> str:
    """Build the checkout's image, save it to archive, and return its tag."""
    engine = choose_engine()
    image_id = build_image(engine, repo, build_secrets(), archive.with_suffix(".iid"))
    # Derived from the content, so a tag always names the same image.
    tag = f"local-{image_id.removeprefix('sha256:')[:12]}"
    tag_image(engine, image_id, f"{image}:{tag}")
    save_image_archive(engine, archive, [f"{image}:{tag}"])
    return tag


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
        image_archive = staging / ref.image_archive.name
        if ref.image is not None:
            if progress is not None:
                progress(f"  building local image {ref.image} from {ref.repo}")
            # As release does: the chart names the image built from its revision.
            values = ChartValues.from_chart_dir(chart)
            values.image.tag = build_local_image(ref.repo, ref.image, image_archive)
            values.write(chart)
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
        if ref.image is not None:
            image_archive.replace(ref.image_archive)
    if progress is not None:
        progress(f"  ready local {ref.label()} at {ref.package}")
