import logging
from collections.abc import Iterable, Mapping, Sequence
from fnmatch import fnmatch
from pathlib import Path
from subprocess import CalledProcessError
from typing import Any

import yaml
from click import ClickException
from pydantic import ValidationError

from zep_dev.cluster import CLUSTER_NAME, helm, kind, load_image_archive
from zep_dev.commands.chart.utils import discover_charts
from zep_dev.models import ChartMetadata
from zep_dev.shared import execute
from zep_dev.static import CT_YAML

LOG = logging.getLogger(__name__)

DEFAULT_EXCLUDES = (
    "registry.k8s.io/*",
    "docker.io/kindest/*",
    "*/pause*",
    "*pause:*",
    "*kindnet*",
    "*coredns*",
    "*local-path*",
    "import-*",
)


def choose_engine() -> str:
    for engine in ("podman", "docker"):
        try:
            execute(
                engine,
                "version",
                capture_stdout=True,
                capture_stderr=True,
                skip_resolve=True,
            )
        except CalledProcessError, OSError:
            continue
        return engine
    raise ClickException("neither podman nor docker is available")


def parse_image_refs(output: str) -> set[str]:
    refs: set[str] = set()
    for line in output.splitlines():
        columns = line.split()
        if not columns:
            continue

        ref = columns[0]
        # ctr emits bare content-address aliases alongside named references.
        # They cannot identify the workload image after the archive is loaded.
        if ref == "REF" or ref.startswith("sha256:"):
            continue

        if "@sha256:" in ref:
            name, digest = ref.split("@sha256:", maxsplit=1)
            if name and digest:
                refs.add(ref)
            continue

        # Split from the right so a registry port is not mistaken for a tag.
        name, separator, tag = ref.rpartition(":")
        if separator and name and tag and "/" not in tag:
            refs.add(ref)

    return refs


def select_image_refs(refs: Iterable[str], includes: Sequence[str]) -> list[str]:
    # Digest references fail when loaded into a fresh cluster, so only include
    # images with tags.
    selected = set()
    for ref in refs:
        name, separator, tag = ref.rpartition(":")
        if separator and name and tag and "/" not in tag and "@" not in ref:
            selected.add(ref)
    if includes:
        selected = {
            ref for ref in selected if any(fnmatch(ref, glob) for glob in includes)
        }
    selected = {
        ref
        for ref in selected
        if not any(fnmatch(ref, glob) for glob in DEFAULT_EXCLUDES)
    }
    return sorted(selected)


def discover_image_refs(engine: str, includes: Sequence[str]) -> list[str]:
    nodes = kind(
        "get", "nodes", "--name", CLUSTER_NAME, capture_stdout=True
    ).stdout.splitlines()

    refs: set[str] = set()
    for node in nodes:
        image_output = execute(
            engine,
            "exec",
            node,
            "ctr",
            "--namespace=k8s.io",
            "images",
            "ls",
            capture_stdout=True,
            skip_resolve=True,
        ).stdout
        refs.update(parse_image_refs(image_output))

    selected = select_image_refs(refs, includes)
    if not selected:
        raise ClickException("no images selected")
    return selected


def dump_images(output: Path, includes: Sequence[str]) -> None:
    engine = choose_engine()
    selected = discover_image_refs(engine, includes)

    LOG.info("Using container engine: %s", engine)
    pull_missing_images(engine, selected)
    save_image_archive(engine, output, selected)


def pack_images(
    helm_dir: Path,
    output: Path,
) -> None:
    if not (helm_dir / CT_YAML).is_file():
        raise ClickException(f"{CT_YAML} is required in the root of --helm-dir")

    refs: set[str] = set()
    for chart_path in discover_charts(helm_dir):
        chart_dir = helm_dir / chart_path
        try:
            metadata = ChartMetadata.from_chart_dir(chart_dir)
        except (ValueError, ValidationError) as error:
            raise ClickException(str(error)) from error
        if metadata.type == "library":
            LOG.info("Skipping library chart: %s", chart_dir)
            continue

        values_files: Sequence[Path | None] = sorted(
            chart_dir.glob("ci/*-values.yaml")
        ) or (None,)
        for values_file in values_files:
            args = ["template", "zep-pack", str(chart_dir)]
            if values_file is not None:
                args.extend(["-f", str(values_file)])
            rendered = helm(*args, capture_stdout=True).stdout
            refs.update(extract_image_refs(rendered))

        kind_values = chart_dir / "ci" / "kind-values.yaml"
        if kind_values.is_file():
            refs.update(extract_image_refs(kind_values.read_text(encoding="utf-8")))

    selected = sorted(refs)
    if not selected:
        LOG.warn("No image references found, not packing anything")
        return

    digest_refs = [ref for ref in selected if "@sha256:" in ref]
    if digest_refs:
        LOG.warning(
            "Images with digests not supported for packing, skipping: %s", digest_refs
        )
    valid_refs = [ref for ref in selected if ref not in digest_refs]
    if not valid_refs:
        LOG.warning("No tagged image references found, not packing anything")
        return
    engine = choose_engine()
    LOG.info("Using container engine: %s", engine)
    pull_missing_images(engine, valid_refs)
    save_image_archive(engine, output, valid_refs)


def extract_image_refs(yaml_text: str) -> set[str]:
    refs: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key == "image" and isinstance(child, str) and child.strip():
                    refs.add(child.strip())
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    try:
        for document in yaml.safe_load_all(yaml_text):
            visit(document)
    except yaml.YAMLError as error:
        raise ClickException("failed to parse YAML while discovering images") from error
    return refs


def pull_missing_images(engine: str, refs: Sequence[str]) -> None:
    for ref in refs:
        result = execute(
            engine,
            "image",
            "inspect",
            ref,
            capture_stdout=True,
            capture_stderr=True,
            skip_resolve=True,
            check=False,
        )
        if result.returncode != 0:
            LOG.info("Pulling image onto host: %s", ref)
            try:
                execute(engine, "pull", ref, skip_resolve=True)
            except CalledProcessError as error:
                raise ClickException(f"failed to pull image: {ref}") from error


def save_image_archive(engine: str, output: Path, refs: Sequence[str]) -> None:
    for ref in refs:
        LOG.info("Including image: %s", ref)
    output.parent.mkdir(parents=True, exist_ok=True)
    save_options = (
        ["--multi-image-archive", "--format", "docker-archive"]
        if engine == "podman"
        else []
    )
    execute(
        engine,
        "save",
        *save_options,
        "-o",
        str(output),
        *refs,
        skip_resolve=True,
    )
    LOG.info("Wrote image archive: %s", output)


def load_images(archive: Path) -> None:
    load_image_archive(archive)
