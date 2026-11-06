"""Archive operations for images in a selected Environment cluster."""

from collections.abc import Iterable, Sequence
from fnmatch import fnmatch
from pathlib import Path

from zep_dev.development_environments.kind import kind, load_image_archive
from zep_dev.development_environments.target import ExecutionTarget
from zep_dev.errors import ZepDevError
from zep_dev.infrastructure.container_engine import (
    choose_engine,
    pull_missing_images,
    save_image_archive,
)
from zep_dev.shared import execute

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


def has_image_tag(ref: str) -> bool:
    name, _, tag = ref.rpartition(":")
    return bool(name and tag) and "/" not in tag


def parse_image_refs(output: str) -> set[str]:
    refs: set[str] = set()
    for line in output.splitlines():
        columns = line.split()
        if not columns:
            continue
        ref = columns[0]
        if ref == "REF" or ref.startswith("sha256:"):
            continue
        if "@sha256:" in ref:
            name, digest = ref.split("@sha256:", maxsplit=1)
            if name and digest:
                refs.add(ref)
            continue
        if has_image_tag(ref):
            refs.add(ref)
    return refs


def select_image_refs(refs: Iterable[str], includes: Sequence[str]) -> list[str]:
    selected = {ref for ref in refs if "@" not in ref and has_image_tag(ref)}
    if includes:
        selected = {
            ref for ref in selected if any(fnmatch(ref, glob) for glob in includes)
        }
    return sorted(
        ref
        for ref in selected
        if not any(fnmatch(ref, pattern) for pattern in DEFAULT_EXCLUDES)
    )


def list_images(
    target: ExecutionTarget, includes: Sequence[str] = (), *, engine: str | None = None
) -> list[str]:
    engine = engine or choose_engine()
    nodes = kind(
        target,
        "get",
        "nodes",
        "--name",
        target.cluster_name,
        engine=engine,
        capture_stdout=True,
    ).stdout.splitlines()
    refs: set[str] = set()
    for node in nodes:
        output = execute(
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
        refs.update(parse_image_refs(output))
    selected = select_image_refs(refs, includes)
    if not selected:
        raise ValueError("no images selected")
    return selected


def dump_images(
    target: ExecutionTarget, output: Path, includes: Sequence[str] = ()
) -> None:
    engine = choose_engine()
    selected = list_images(target, includes, engine=engine)
    pull_missing_images(engine, selected)
    save_image_archive(engine, output, selected)


def load_images(target: ExecutionTarget, archive: Path) -> None:
    if not archive.is_file() or archive.stat().st_size == 0:
        raise ZepDevError(f"image archive is missing or empty: {archive}")
    load_image_archive(target, archive)
