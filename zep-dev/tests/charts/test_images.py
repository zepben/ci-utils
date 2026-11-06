from pathlib import Path

import pytest

from tests.support.charts import write_chart
from tests.support.execution import FakeExecuteFactory
from zep_dev.charts import images as chart_images
from zep_dev.infrastructure import container_engine


def test_pack_skips_digest_only_charts(
    helm_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    chart = write_chart(
        helm_dir / "charts" / "digest-app",
        {"name": "digest-app", "version": "1.0.0"},
    )
    fake_execute(chart_images).on(
        "helm",
        "template",
        "zep-pack",
        str(chart),
        stdout="image: ghcr.io/example/app@sha256:abc\n",
    )
    monkeypatch.setattr(
        chart_images,
        "choose_engine",
        lambda: (_ for _ in ()).throw(AssertionError("engine selected")),
    )
    output = tmp_path / "images.tar"
    chart_images.pack_images(helm_dir, output)
    assert not output.exists()


def test_pack_renders_ci_values_and_saves_selected_images(
    helm_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    chart = write_chart(
        helm_dir / "charts" / "app", {"name": "app", "version": "1.0.0"}
    )
    values = chart / "ci" / "kind-values.yaml"
    values.parent.mkdir()
    values.write_text("image: example/helper:2\n", encoding="utf-8")
    monkeypatch.setattr(chart_images, "choose_engine", lambda: "podman")
    render = fake_execute(chart_images).on(
        "helm", "template", "zep-pack", stdout="image: example/app:1\n"
    )
    host = (
        fake_execute(container_engine)
        .on("podman", "image", "inspect")
        .on("podman", "save")
    )
    output = tmp_path / "images.tar"
    chart_images.pack_images(helm_dir, output)
    [rendered] = render.calls_for("helm", "template")
    assert rendered.args == (
        "helm",
        "template",
        "zep-pack",
        str(chart),
        "-f",
        str(values),
    )
    [save] = host.calls_for("podman", "save")
    assert save.args[:7] == (
        "podman",
        "save",
        "--multi-image-archive",
        "--format",
        "docker-archive",
        "-o",
        str(output),
    )
    assert sorted(save.args[7:]) == ["example/app:1", "example/helper:2"]
