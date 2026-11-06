"""Pack images referenced by local application charts."""

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

import yaml

from zep_dev.charts.utils import discover_charts
from zep_dev.errors import ZepDevError
from zep_dev.infrastructure.container_engine import (
    choose_engine,
    pull_missing_images,
    save_image_archive,
)
from zep_dev.models import ChartMetadata
from zep_dev.shared import execute
from zep_dev.static import CT_YAML

LOG = logging.getLogger(__name__)


def extract_image_refs(yaml_text: str) -> set[str]:
    refs: set[str] = set()

    def visit(value: object) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key == "image" and isinstance(child, str) and child.strip():
                    refs.add(child.strip())
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for document in yaml.safe_load_all(yaml_text):
        visit(document)
    return refs


def pack_images(helm_dir: Path, output: Path) -> None:
    if not (helm_dir / CT_YAML).is_file():
        raise ZepDevError(f"{CT_YAML} is required in the root of --helm-dir")

    refs: set[str] = set()
    for chart_path in discover_charts(helm_dir):
        chart_dir = helm_dir / chart_path
        metadata = ChartMetadata.from_chart_dir(chart_dir)
        if metadata.type == "library":
            LOG.info("Skipping library chart: %s", chart_dir)
            continue
        values_files: Sequence[Path | None] = sorted(
            chart_dir.glob("ci/*-values.yaml")
        ) or (None,)
        for values_file in values_files:
            args = ["helm", "template", "zep-pack", str(chart_dir)]
            if values_file is not None:
                args.extend(["-f", str(values_file)])
            refs.update(extract_image_refs(execute(*args, capture_stdout=True).stdout))
        kind_values = chart_dir / "ci" / "kind-values.yaml"
        if kind_values.is_file():
            refs.update(extract_image_refs(kind_values.read_text(encoding="utf-8")))

    if not refs:
        LOG.warning("No image references found, not packing anything")
        return
    digest_refs = sorted(ref for ref in refs if "@sha256:" in ref)
    if digest_refs:
        LOG.warning(
            "Images with digests not supported for packing, skipping: %s", digest_refs
        )
    selected = sorted(refs.difference(digest_refs))
    if not selected:
        LOG.warning("No tagged image references found, not packing anything")
        return
    engine = choose_engine()
    pull_missing_images(engine, selected)
    save_image_archive(engine, output, selected)
    LOG.info("Wrote image archive: %s", output)
