import logging
from collections.abc import Iterable, Sequence
from fnmatch import fnmatch
from pathlib import Path
from subprocess import CalledProcessError

from click import ClickException

from zep_dev.cluster import CLUSTER_NAME, kind
from zep_dev.shared import execute

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
    for ref in selected:
        LOG.info("Including image: %s", ref)
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

    output.parent.mkdir(parents=True, exist_ok=True)
    save_options = ["--multi-image-archive"] if engine == "podman" else []
    execute(
        engine,
        "save",
        *save_options,
        "-o",
        str(output),
        *selected,
        skip_resolve=True,
    )
    LOG.info("Wrote image archive: %s", output)


def load_images(archive: Path) -> None:
    if not archive.is_file() or archive.stat().st_size == 0:
        raise ClickException(f"image archive is missing or empty: {archive}")
    kind("load", "image-archive", str(archive), "--name", CLUSTER_NAME)
