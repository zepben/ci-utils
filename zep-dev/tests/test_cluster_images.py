from pathlib import Path
from unittest.mock import call

import pytest
import yaml
from click import ClickException
from click.testing import CliRunner

from _charts import write_chart
from _fake_execute import FakeExecute, FakeExecuteFactory
from zep_dev import cluster, cluster_images
from zep_dev.groups.cluster import pack_images as pack_images_command
from zep_dev.shared import CommandResult


def write_application(
    path: Path,
    *,
    name: str,
    chart: str,
    value_files: list[str],
    release_name: str | None = None,
) -> Path:
    helm: dict[str, object] = {"valueFiles": value_files}
    if release_name is not None:
        helm["releaseName"] = release_name
    manifest = {
        "apiVersion": "argoproj.io/v1alpha1",
        "kind": "Application",
        "metadata": {"name": name},
        "spec": {
            "sources": [
                {
                    "repoURL": "ghcr.io/zepben/charts",
                    "chart": chart,
                    "targetRevision": "1.2.3",
                    "helm": helm,
                },
                {
                    "repoURL": "https://example.invalid/deployments.git",
                    "ref": "deployments",
                },
            ],
            "destination": {"namespace": "staging"},
        },
    }
    path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    return path


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


def test_pack_applications_renders_all_and_packs_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deployments = tmp_path / "deployments"
    deployments.mkdir()
    first_values = deployments / "first.yaml"
    second_values = deployments / "second.yaml"
    first_values.write_text(
        "worker:\n  image: ghcr.io/example/configured:1\n",
        encoding="utf-8",
    )
    second_values.write_text("second: true\n", encoding="utf-8")
    first_app = write_application(
        tmp_path / "first-app.yaml",
        name="first-app",
        chart="first",
        value_files=["$deployments/first.yaml", "$deployments/second.yaml"],
        release_name="first-release",
    )
    second_app = write_application(
        tmp_path / "second-app.yaml",
        name="second-app",
        chart="second",
        value_files=["$deployments/second.yaml"],
    )
    helm = (
        FakeExecute()
        .on(
            "template",
            "first-release",
            "oci://ghcr.io/zepben/charts/first",
            stdout=(
                "Pulled: ghcr.io/zepben/charts/first:1.2.3\n"
                "Digest: sha256:abc\n"
                "oci://ghcr.io/zepben/charts/first:1.2.3 contains an underscore.\n"
                "---\n"
                "containers:\n"
                "  - image: ghcr.io/example/shared:1\n"
                "  - image: ghcr.io/example/first:1\n"
            ),
        )
        .on(
            "template",
            "second-app",
            "oci://ghcr.io/zepben/charts/second",
            stdout=(
                "containers:\n"
                "  - image: ghcr.io/example/shared:1\n"
                "  - image: ghcr.io/example/second:1\n"
            ),
        )
    )
    monkeypatch.setattr(cluster_images, "helm", helm)
    packed: list[tuple[set[str], Path]] = []
    monkeypatch.setattr(
        cluster_images,
        "pack_image_refs",
        lambda refs, output: packed.append((set(refs), output)),
    )
    output = tmp_path / "images.tar"

    cluster_images.pack_applications(
        [first_app, second_app],
        [f"deployments={deployments}"],
        output,
    )

    assert helm.calls == [
        call(
            "template",
            "first-release",
            "oci://ghcr.io/zepben/charts/first",
            "--version",
            "1.2.3",
            "--namespace",
            "staging",
            "-f",
            str(first_values),
            "-f",
            str(second_values),
            capture_stdout=True,
        ),
        call(
            "template",
            "second-app",
            "oci://ghcr.io/zepben/charts/second",
            "--version",
            "1.2.3",
            "--namespace",
            "staging",
            "-f",
            str(second_values),
            capture_stdout=True,
        ),
    ]
    assert packed == [
        (
            {
                "ghcr.io/example/first:1",
                "ghcr.io/example/second:1",
                "ghcr.io/example/shared:1",
                "ghcr.io/example/configured:1",
            },
            output,
        )
    ]


def test_pack_cli_rejects_helm_dir_with_application(tmp_path: Path) -> None:
    application = tmp_path / "application.yaml"
    application.touch()

    result = CliRunner().invoke(
        pack_images_command,
        [
            "--helm-dir",
            str(tmp_path),
            "--output",
            "images.tar",
            str(application),
        ],
    )

    assert result.exit_code == 2
    assert "--helm-dir cannot be combined with Application paths" in result.output


def test_pack_cli_accepts_application_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applications = [tmp_path / "first.yaml", tmp_path / "second.yaml"]
    for application in applications:
        application.touch()
    calls: list[tuple[tuple[Path, ...], tuple[str, ...], Path]] = []
    monkeypatch.setattr(
        cluster_images,
        "pack_applications",
        lambda apps, refs, output: calls.append((apps, refs, output)),
    )

    result = CliRunner().invoke(
        pack_images_command,
        [
            "--output",
            "images.tar",
            *(str(path) for path in applications),
        ],
    )

    assert result.exit_code == 0
    assert calls == [(tuple(applications), (), Path("images.tar"))]


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
