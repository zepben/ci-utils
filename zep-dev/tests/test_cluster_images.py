from pathlib import Path
from unittest.mock import call

import pytest
from click import ClickException

from _charts import write_chart
from _fake_execute import FakeExecute, FakeExecuteFactory
from zep_dev import cluster, cluster_images
from zep_dev.shared import CommandResult


def test_parse_image_refs() -> None:
    output = """\
REF TYPE DIGEST
ghcr.io/example/app:1.2 application/test sha256:one
localhost:5000/example/api:latest application/test sha256:two
ghcr.io/example/app@sha256:abc application/test sha256:abc
sha256:abc application/test sha256:abc
localhost:5000/example/untagged application/test sha256:three
"""

    assert cluster_images.parse_image_refs(output) == {
        "ghcr.io/example/app:1.2",
        "ghcr.io/example/app@sha256:abc",
        "localhost:5000/example/api:latest",
    }


def test_select_image_refs() -> None:
    refs = {
        "docker.io/curlimages/curl:8.11.1",
        "docker.io/kindest/kindnetd:v1",
        "ghcr.io/example/app:1.2",
        "ghcr.io/example/app@sha256:abc",
        "ghcr.io/example/digest-only@sha256:def",
        "ghcr.io/example/untagged",
        "import-2026-09-11@sha256:123",
        "registry.k8s.io/pause:3.10",
    }

    assert cluster_images.select_image_refs(refs, ()) == [
        "docker.io/curlimages/curl:8.11.1",
        "ghcr.io/example/app:1.2",
    ]
    assert cluster_images.select_image_refs(refs, ("ghcr.io/example/*",)) == [
        "ghcr.io/example/app:1.2",
    ]


def test_choose_engine_falls_back_to_docker(
    fake_execute: FakeExecuteFactory,
) -> None:
    fake_execute(cluster_images).on(
        "podman", "version", raises=FileNotFoundError("podman")
    ).on("docker", "version")

    assert cluster_images.choose_engine() == "docker"


def test_discover_image_refs_collects_all_nodes(
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    fake_kind = FakeExecute().on(
        "get",
        "nodes",
        stdout="test-cluster-control-plane\ntest-cluster-worker\n",
    )
    fake_execute(cluster_images).on(
        "podman",
        "exec",
        "test-cluster-control-plane",
        stdout="ghcr.io/example/api:1.2 application/test\n"
        "registry.k8s.io/pause:3.10 application/test\n",
    ).on(
        "podman",
        "exec",
        "test-cluster-worker",
        stdout="ghcr.io/example/worker:1.2 application/test\n",
    )
    monkeypatch.setattr(cluster_images, "kind", fake_kind)

    assert cluster_images.discover_image_refs("podman", ("ghcr.io/example/*",)) == [
        "ghcr.io/example/api:1.2",
        "ghcr.io/example/worker:1.2",
    ]


def test_discover_image_refs_rejects_empty_selection(
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    monkeypatch.setattr(
        cluster_images,
        "kind",
        lambda *args, **kwargs: CommandResult(0, "test-cluster-worker\n", ""),
    )
    fake_execute(cluster_images).on(
        "podman",
        "exec",
        stdout="registry.k8s.io/pause:3.10 application/test\n",
    )

    with pytest.raises(ClickException, match="no images selected"):
        cluster_images.discover_image_refs("podman", ())


def test_extract_image_refs_recurses_through_documents() -> None:
    rendered = """\
image: ghcr.io/example/api:1.2
sidecars:
  - image: ghcr.io/example/worker:1.2
  - image: " "
ignored:
  image:
    repository: ghcr.io/example/not-a-reference
---
nested:
  image: ghcr.io/example/api:1.2
  deeper:
    image: 42
"""

    assert cluster_images.extract_image_refs(rendered) == {
        "ghcr.io/example/api:1.2",
        "ghcr.io/example/worker:1.2",
    }


def test_pack_images_does_not_create_archive_without_packable_images(
    helm_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chart = write_chart(
        helm_dir / "charts" / "digest-app",
        {"name": "digest-app", "version": "1.0.0"},
    )
    helm = FakeExecute().on(
        "template",
        "zep-pack",
        str(chart),
        stdout="image: ghcr.io/example/app@sha256:abc\n",
    )
    monkeypatch.setattr(cluster_images, "helm", helm)

    def unexpected_engine_selection() -> str:
        raise AssertionError("container engine must not be selected")

    monkeypatch.setattr(cluster_images, "choose_engine", unexpected_engine_selection)
    output = tmp_path / "images.tar"

    cluster_images.pack_images(helm_dir, output)

    assert not output.exists()


@pytest.mark.parametrize(
    ("engine_name", "save_options"),
    [
        ("podman", ("--multi-image-archive", "--format", "docker-archive")),
        ("docker", ()),
    ],
)
def test_dump_images_pulls_missing_images_and_saves(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    engine_name: str,
    save_options: tuple[str, ...],
) -> None:
    selected = [
        "docker.io/curlimages/curl:8.11.1",
        "ghcr.io/example/app:1.2",
    ]
    monkeypatch.setattr(cluster_images, "choose_engine", lambda: engine_name)
    monkeypatch.setattr(
        cluster_images, "discover_image_refs", lambda engine, includes: selected
    )
    engine = (
        fake_execute(cluster_images)
        .on(
            engine_name,
            "image",
            "inspect",
            "docker.io/curlimages/curl:8.11.1",
            returncode=1,
        )
        .on(engine_name, "image", "inspect", "ghcr.io/example/app:1.2")
        .on(engine_name, "pull", "docker.io/curlimages/curl:8.11.1")
        .on(engine_name, "save", *save_options, "-o")
    )
    output = tmp_path / "archives" / "images.tar"

    cluster_images.dump_images(output, ())

    assert output.parent.is_dir()
    assert len(engine.calls_for(engine_name, "pull")) == 1
    [save_call] = engine.calls_for(engine_name, "save")
    assert save_call.args == (
        engine_name,
        "save",
        *save_options,
        "-o",
        str(output),
        *selected,
    )


def test_load_images_validates_archive_and_loads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    kind = FakeExecute().on("load", "image-archive")
    monkeypatch.setattr(cluster, "kind", kind)
    missing = tmp_path / "missing.tar"
    empty = tmp_path / "empty.tar"
    empty.touch()

    for invalid in missing, empty:
        with pytest.raises(ClickException, match="missing or empty"):
            cluster_images.load_images(invalid)

    archive = tmp_path / "images.tar"
    archive.write_bytes(b"archive")
    cluster_images.load_images(archive)

    assert kind.calls == [
        call(
            "load",
            "image-archive",
            str(archive),
            "--name",
            "test-cluster",
        )
    ]
