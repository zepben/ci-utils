"""Choose an available host container engine."""

import os
from collections.abc import Sequence
from pathlib import Path
from subprocess import CalledProcessError

from zep_dev.errors import ZepDevError
from zep_dev.shared import execute


def choose_engine() -> str:
    provider = os.environ.get("KIND_EXPERIMENTAL_PROVIDER")
    if provider:
        if provider not in {"podman", "docker"}:
            raise ValueError(
                f"Unsupported KIND_EXPERIMENTAL_PROVIDER={provider!r}; "
                "expected podman or docker"
            )
        return provider
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
    raise ZepDevError("neither podman nor docker is available")


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
            execute(engine, "pull", ref, skip_resolve=True)


def save_image_archive(engine: str, output: Path, refs: Sequence[str]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    save_options = (
        ["--multi-image-archive", "--format", "docker-archive"]
        if engine == "podman"
        else []
    )
    execute(engine, "save", *save_options, "-o", str(output), *refs, skip_resolve=True)
