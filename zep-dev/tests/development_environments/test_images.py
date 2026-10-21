from pathlib import Path

import pytest

from tests.support.execution import FakeExecuteFactory
from zep_dev.development_environments import images, kind
from zep_dev.development_environments.target import ExecutionTarget
from zep_dev.infrastructure import container_engine
from zep_dev.shared import CommandResult


def test_image_selection_excludes_cluster_and_digest_references() -> None:
    refs = images.parse_image_refs(
        "REF TYPE\n"
        "ghcr.io/example/app:1.2 image\n"
        "ghcr.io/example/app@sha256:abc image\n"
        "registry.k8s.io/pause:3.10 image\n"
    )
    assert images.select_image_refs(refs, ()) == ["ghcr.io/example/app:1.2"]


def test_list_images_uses_selected_cluster(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake_execute: FakeExecuteFactory
) -> None:
    first = ExecutionTarget("first", tmp_path)
    second = ExecutionTarget("second", tmp_path)
    monkeypatch.setattr(images, "choose_engine", lambda: "podman")
    calls: list[tuple[ExecutionTarget, tuple[str, ...]]] = []

    def list_nodes(
        target: ExecutionTarget, *args: str, **_kwargs: object
    ) -> CommandResult:
        calls.append((target, args))
        return CommandResult(0, "worker\n", "")

    monkeypatch.setattr(images, "kind", list_nodes)
    fake_execute(images).on(
        "podman", "exec", "worker", stdout="ghcr.io/example/app:1.2 image\n"
    )
    assert images.list_images(first) == ["ghcr.io/example/app:1.2"]
    assert images.list_images(second) == ["ghcr.io/example/app:1.2"]
    assert calls == [
        (first, ("get", "nodes", "--name", first.cluster_name)),
        (second, ("get", "nodes", "--name", second.cluster_name)),
    ]


@pytest.mark.parametrize(
    ("engine", "options"),
    [
        ("podman", ("--multi-image-archive", "--format", "docker-archive")),
        ("docker", ()),
    ],
)
def test_dump_pulls_missing_and_saves(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
    engine: str,
    options: tuple[str, ...],
) -> None:
    target = ExecutionTarget("first", tmp_path)
    monkeypatch.setattr(images, "choose_engine", lambda: engine)
    monkeypatch.setattr(
        images, "list_images", lambda *_args, **_kwargs: ["example/app:1"]
    )
    fake = (
        fake_execute(container_engine)
        .on(engine, "image", "inspect", returncode=1)
        .on(engine, "pull")
        .on(engine, "save")
    )
    output = tmp_path / "archives" / "images.tar"
    images.dump_images(target, output)
    assert output.parent.is_dir()
    [pull] = fake.calls_for(engine, "pull")
    [save] = fake.calls_for(engine, "save")
    assert pull.args == (engine, "pull", "example/app:1")
    assert fake.calls.index(pull) < fake.calls.index(save)
    assert save.args == (
        engine,
        "save",
        *options,
        "-o",
        str(output),
        "example/app:1",
    )


def test_load_validates_archive_and_uses_selected_cluster(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = ExecutionTarget("first", tmp_path)
    called: list[tuple[str, ...]] = []

    def load(target: ExecutionTarget, *args: str) -> CommandResult:
        called.append((target.name, *args))
        return CommandResult(0, "", "")

    monkeypatch.setattr(kind, "kind", load)
    with pytest.raises(ValueError, match="missing or empty"):
        images.load_images(target, tmp_path / "missing.tar")
    archive = tmp_path / "images.tar"
    archive.write_bytes(b"archive")
    images.load_images(target, archive)
    assert called == [
        ("first", "load", "image-archive", str(archive), "--name", "zep-dev-first")
    ]
