"""Working-tree chart builds and local artifact selection, with tool boundaries stubbed."""

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from click.testing import CliRunner
from pydantic import ValidationError

from tests.support.charts import published_chart
from tests.support.execution import FakeExecute, FakeExecuteFactory, option_value
from tests.support.fixtures import PrepareKind, WriteDistribution
from tests.support.git import commit_all, git, init_repository
from zep_dev.charts import published
from zep_dev.cli import cli
from zep_dev.development_environments import (
    helm,
    lifecycle,
    local_charts,
)
from zep_dev.development_environments.chart_sources import ChartResolver
from zep_dev.development_environments.distributions import Distribution, LocalLocator
from zep_dev.development_environments.local_charts import LocalChartRef
from zep_dev.development_environments.target import execution_target
from zep_dev.errors import ZepDevError


@pytest.fixture
def checkout(tmp_path: Path, state_home: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "checkout"
    chart = repo / "helm/charts/ewb"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text(
        "apiVersion: v2\nname: ewb\nversion: 0.1.0\nappVersion: unchanged\n"
        "dependencies:\n- name: common\n  version: 0.0.5\n"
        "  repository: oci://ghcr.io/zepben/helm-commons\n"
        "- name: sibling\n  version: 0.1.0\n  repository: file://../sibling\n"
    )
    (chart / "values.yaml").write_text("image:\n  tag: original\n")
    sibling = chart.parent / "sibling"
    sibling.mkdir()
    (sibling / "Chart.yaml").write_text(
        "apiVersion: v2\nname: sibling\nversion: 0.1.0\n"
    )
    init_repository(repo)
    commit_all(repo, "Initial chart")
    git("tag", "v1.2.3", cwd=repo)
    monkeypatch.chdir(chart)
    return repo


@pytest.fixture
def build_tools(checkout: Path, fake_execute: FakeExecuteFactory) -> FakeExecute:
    def dependency_build(args: tuple[str, ...], _kwargs: dict[str, object]) -> None:
        chart = Path(args[3])
        assert chart != checkout / "helm/charts/ewb"
        assert (chart.parent / "sibling/Chart.yaml").is_file()
        (chart / "Chart.lock").write_text("generated in staging")

    def package(args: tuple[str, ...], _kwargs: dict[str, object]) -> None:
        chart = Path(args[2])
        metadata = yaml.safe_load((chart / "Chart.yaml").read_text())
        assert metadata["appVersion"] == "unchanged"
        version = option_value(args, "--version")
        destination = Path(option_value(args, "--destination"))
        (destination / f"ewb-{version}.tgz").write_text(
            (chart / "values.yaml").read_text() + (chart / "untracked.yaml").read_text()
        )

    (checkout / "helm/charts/ewb/untracked.yaml").write_text("new untracked input\n")
    return (
        fake_execute(local_charts)
        .on("git", "rev-parse", stdout=str(checkout))
        .on("helm", "dependency", "build", hook=dependency_build)
        .on("helm", "package", hook=package)
    )


@pytest.mark.parametrize("value", [False, "true", 1, None, {}])
def test_local_locator_requires_literal_boolean_true(value: object) -> None:
    with pytest.raises(ValidationError):
        LocalLocator.model_validate({"local": value})


def test_local_locator_cannot_be_combined_with_another_locator() -> None:
    with pytest.raises(ValidationError):
        Distribution.model_validate(
            {
                "metadata": {"name": "test"},
                "charts": {
                    "ewb": {"local": True, "version": "1.2.3"},
                },
            }
        )


def test_resolve_uses_caller_checkout_from_subdirectory_and_detached_head(
    checkout: Path,
    state_home: Path,
) -> None:
    subprocess.run(
        ["git", "-C", str(checkout), "checkout", "--detach", "-q"], check=True
    )
    ref = ChartResolver().resolve("ewb", LocalLocator(local=True))
    assert isinstance(ref, LocalChartRef)
    assert ref.repo == checkout
    assert ref.version == "1.2.3"
    assert ref.package == state_home / "zep-dev/charts/ewb/1.2.3/ewb-1.2.3.tgz"
    with pytest.raises(ValueError, match="Chart.yaml not found"):
        ChartResolver().resolve("eas", LocalLocator(local=True))


def test_local_chart_name_must_match_selection(checkout: Path) -> None:
    path = checkout / "helm/charts/ewb/Chart.yaml"
    path.write_text(path.read_text().replace("name: ewb", "name: eas"))
    with pytest.raises(ValueError, match="Expected chart ewb"):
        ChartResolver().resolve("ewb", LocalLocator(local=True))


def test_build_replaces_dirty_version_and_preserves_sources(
    checkout: Path,
    build_tools: FakeExecute,
) -> None:
    resolver = ChartResolver()
    ref = resolver.resolve("ewb", LocalLocator(local=True))
    assert isinstance(ref, LocalChartRef)
    values = checkout / "helm/charts/ewb/values.yaml"
    values.write_text("image:\n  tag: manually-selected-sha\n")
    resolver.ensure(ref)
    assert "manually-selected-sha" in ref.package.read_text()
    assert "new untracked input" in ref.package.read_text()
    values.write_text("image:\n  tag: another-image\n")
    resolver.ensure(ref)
    assert "another-image" in ref.package.read_text()
    assert len(build_tools.calls_for("helm", "package")) == 2
    assert not (values.parent / "Chart.lock").exists()
    assert "version: 0.1.0" in (values.parent / "Chart.yaml").read_text()
    assert not list(ref.package.parent.glob(".build-*"))
    resolver.check(ref)


@pytest.mark.parametrize("step", ["dependency", "package"])
def test_failed_build_preserves_previous_package(
    checkout: Path,
    fake_execute: FakeExecuteFactory,
    step: str,
) -> None:
    resolver = ChartResolver()
    ref = resolver.resolve("ewb", LocalLocator(local=True))
    assert isinstance(ref, LocalChartRef)
    ref.package.parent.mkdir(parents=True)
    ref.package.write_bytes(b"previous successful package")
    fake = fake_execute(local_charts)
    fake.on("helm", step, returncode=1, stderr="build failed")
    fake.on("helm", "dependency", "build")
    with pytest.raises(subprocess.CalledProcessError):
        resolver.ensure(ref)
    assert ref.package.read_bytes() == b"previous successful package"
    assert not list(ref.package.parent.glob(".build-*"))


def test_new_commit_requires_new_package(checkout: Path) -> None:
    resolver = ChartResolver()
    original = resolver.resolve("ewb", LocalLocator(local=True))
    assert isinstance(original, LocalChartRef)
    original.package.parent.mkdir(parents=True)
    original.package.write_bytes(b"old chart")
    commit_all(checkout, "Next commit")
    current = resolver.resolve("ewb", LocalLocator(local=True))
    assert current.version != original.version
    with pytest.raises(ZepDevError, match="run distribution build first"):
        resolver.check(current)


def test_local_install_uses_package_and_existing_values(checkout: Path) -> None:
    ref = ChartResolver().resolve("ewb", LocalLocator(local=True))
    assert isinstance(ref, LocalChartRef)
    values = checkout / "overrides.yaml"
    target = execution_target("integration")
    args = helm.application_install_args(target, ref, values)
    assert args[:5] == ["helm", "upgrade", "--install", "ewb", str(ref.package)]
    assert "--version" not in args
    assert option_value(args, "-f") == str(values)
    assert option_value(args, "--kubeconfig") == str(target.kubeconfig)


def test_missing_local_package_stops_creation_before_cluster_access(
    checkout: Path,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    write_distribution: WriteDistribution,
    prepare_kind: PrepareKind,
) -> None:
    path = write_distribution(ewb={"local": True})
    basic_template["distribution"] = str(path)
    cluster = prepare_kind()
    with pytest.raises(ZepDevError, match="Missing local chart"):
        lifecycle.create_environment(write_template(basic_template))
    assert cluster.calls == []


@pytest.mark.usefixtures("cli_environment", "registry_auth")
def test_mixed_distribution_build_and_preflight(
    checkout: Path,
    build_tools: FakeExecute,
    write_distribution: WriteDistribution,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    fake_execute: FakeExecuteFactory,
) -> None:
    distribution = write_distribution(ewb={"local": True}, eas={"version": "2.0.0"})
    original = distribution.read_bytes()
    remote = fake_execute(published).on(
        "helm", "show", "chart", stdout=published_chart("eas", "2.0.0")
    )
    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(distribution)]
    )
    assert result.exit_code == 0, result.exception or result.output
    assert distribution.read_bytes() == original
    assert len(build_tools.calls_for("helm", "package")) == 1
    basic_template["distribution"] = str(distribution)
    plan = lifecycle.preflight(write_template(basic_template))
    assert isinstance(plan.charts[0], LocalChartRef)
    assert plan.charts[1].chart.endswith("/eas")
    assert len(build_tools.calls_for("helm", "package")) == 1
    assert all(call.args[3].endswith("/eas") for call in remote.calls)


@pytest.mark.parametrize("output", [None, b""])
def test_missing_or_empty_build_output_preserves_previous_package(
    checkout: Path,
    fake_execute: FakeExecuteFactory,
    output: bytes | None,
) -> None:
    resolver = ChartResolver()
    ref = resolver.resolve("ewb", LocalLocator(local=True))
    assert isinstance(ref, LocalChartRef)
    ref.package.parent.mkdir(parents=True)
    ref.package.write_bytes(b"previous successful package")

    def package(args: tuple[str, ...], _kwargs: dict[str, object]) -> None:
        if output is not None:
            (Path(option_value(args, "--destination")) / ref.package.name).write_bytes(
                output
            )

    fake_execute(local_charts).on("helm", "dependency", "build").on(
        "helm",
        "package",
        hook=package,
    )
    with pytest.raises(RuntimeError, match="did not produce a chart package"):
        resolver.ensure(ref)
    assert ref.package.read_bytes() == b"previous successful package"
    assert not list(ref.package.parent.glob(".build-*"))


@pytest.mark.parametrize(
    "dependencies",
    [
        [],
        [
            {
                "name": "common",
                "version": "0.0.5",
                "repository": "https://example.org/charts",
            }
        ],
    ],
)
def test_build_delegates_dependencies_to_helm_without_test_configuration(
    checkout: Path,
    build_tools: FakeExecute,
    dependencies: list[dict[str, str]],
) -> None:
    metadata_path = checkout / "helm/charts/ewb/Chart.yaml"
    metadata = yaml.safe_load(metadata_path.read_text())
    metadata["dependencies"] = dependencies
    metadata_path.write_text(yaml.safe_dump(metadata))
    # Even an invalid testing configuration must not affect chart packaging.
    (checkout / "helm/ct.yaml").write_text("invalid: [")
    resolver = ChartResolver()
    ref = resolver.resolve("ewb", LocalLocator(local=True))
    resolver.ensure(ref)
    [dependency_build] = build_tools.calls_for("helm", "dependency", "build")
    [package] = build_tools.calls_for("helm", "package")
    assert build_tools.calls.index(dependency_build) < build_tools.calls.index(package)
    assert build_tools.calls_for("helm", "repo") == []


def test_empty_saved_package_is_rejected(checkout: Path) -> None:
    resolver = ChartResolver()
    ref = resolver.resolve("ewb", LocalLocator(local=True))
    assert isinstance(ref, LocalChartRef)
    ref.package.parent.mkdir(parents=True)
    ref.package.touch()
    with pytest.raises(ZepDevError, match="Missing local chart"):
        resolver.check(ref)
