from pathlib import Path
from unittest.mock import call

import pytest
import yaml
from click import ClickException
from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute, FakeExecuteFactory
from zep_dev import cluster, cluster_images
from zep_dev.groups.cluster import images
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
spec:
  imageName: ghcr.io/example/postgresql:16
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
        "ghcr.io/example/postgresql:16",
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


@pytest.mark.parametrize(
    ("include_charts", "list_only"), [(True, True), (False, True), (True, False)]
)
def test_pack_discovers_and_optionally_saves(
    helm_dir: Path,
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    include_charts: bool,
    list_only: bool,
) -> None:
    write_chart(helm_dir / "charts" / "rabbit", {"name": "rabbit", "version": "1.0.0"})
    components = tmp_path / "components.yaml"
    components.write_text("""\
helm_repos:
  argo: https://example.com/argo
cluster_components:
  - name: argo
    chart: argo/argo-cd
    version: '10.3.2'
    namespace: argo-cd
    values:
      redis:
        enabled: true
  - name: cnpg
    chart: ./cnpg
    version: '0.28.0'
    namespace: cnpg-system
""")
    values_files: list[Path] = []

    def check_values(args: tuple[str, ...], kwargs: dict[str, object]) -> None:
        values = Path(args[-1])
        assert yaml.safe_load(values.read_text()) == {"redis": {"enabled": True}}
        values_files.append(values)

    helm = fake_execute(cluster)
    helm.on("helm", "repo", "list").on("helm", "repo", "add").on(
        "helm", "repo", "update"
    )
    helm.on("helm", "template", "zep-pack", stdout="image: rabbitmq:4.1-management\n")
    helm.on(
        "helm",
        "template",
        "argo",
        "argo/argo-cd",
        "--namespace",
        "argo-cd",
        "--version",
        "10.3.2",
        "-f",
        stdout="initContainers:\n- image: redis:8\ncontainers:\n- image: redis:8\n- image: excluded@sha256:abc\n",
        hook=check_values,
    )
    helm.on(
        "helm",
        "template",
        "cnpg",
        str(tmp_path / "cnpg"),
        "--namespace",
        "cnpg-system",
        "--version",
        "0.28.0",
        stdout="image: cnpg:1\n",
    )
    # An empty fake rejects any engine access in list-only mode.
    engine = fake_execute(cluster_images)
    if not list_only:
        engine.on("podman", "version").on("podman", "image", "inspect", returncode=1)
        engine.on("podman", "pull").on("podman", "save")
    output = tmp_path / "images.tar"
    arguments = ["pack", "--components", str(components), "--output", str(output)]
    if include_charts:
        arguments.extend(["--helm-dir", str(helm_dir)])
    if list_only:
        arguments.append("--list-only")
    result = CliRunner().invoke(images, arguments)
    assert result.exit_code == 0, result.output
    expected = (
        ["cnpg:1", "rabbitmq:4.1-management", "redis:8"]
        if include_charts
        else ["cnpg:1", "redis:8"]
    )
    assert all(c.kwargs["capture_stdout"] for c in helm.calls)
    assert values_files and all(not path.exists() for path in values_files)
    if list_only:
        assert result.stdout.splitlines() == expected
        assert not engine.calls
        assert not output.exists()
    else:
        [saved] = engine.calls_for("podman", "save")
        assert saved.args[7:] == tuple(expected)
        assert [c.args[-1] for c in engine.calls_for("podman", "pull")] == expected


@pytest.mark.parametrize(
    ("with_source", "message"),
    [(False, "at least one"), (True, "--output is required")],
)
def test_pack_requires_source_and_output(
    helm_dir: Path, with_source: bool, message: str
) -> None:
    arguments = (
        ["pack", "--helm-dir", str(helm_dir)]
        if with_source
        else ["pack", "--list-only"]
    )
    result = CliRunner().invoke(images, arguments)
    assert result.exit_code == 2
    assert message in result.output


@pytest.mark.parametrize("alias", [None, "database"])
def test_dependency_build_replaces_stale_archives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, alias: str | None
) -> None:
    dependency = {
        "name": "postgresql",
        "version": "2.0.0",
        "repository": "https://example.com",
    }
    if alias is not None:
        dependency["alias"] = alias
    chart = write_chart(
        tmp_path / "app",
        {
            "name": "app",
            "version": "1.0.0",
            "dependencies": [dependency],
        },
    )
    (chart / "charts").mkdir()
    (chart / "charts" / "postgresql-1.0.0.tgz").write_bytes(b"stale archive")
    helm = FakeExecute().on("dependency", "build", str(chart))
    monkeypatch.setattr(cluster_images, "helm", helm)

    cluster_images.prepare_chart_dependencies(chart)

    assert helm.calls == [call("dependency", "build", str(chart), capture_stdout=True)]
