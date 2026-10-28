from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from tests.support.execution import FakeExecute, FakeExecuteFactory, option_value
from tests.support.fixtures import PrepareKind, WriteDistribution
from tests.support.resolvers import RecordingChartResolver
from zep_dev.development_environments import (
    chart_sources,
    cnpg,
    helm,
    kind,
    lifecycle,
    secrets,
    terraform,
)
from zep_dev.development_environments.chart_sources import (
    ChartRef,
    SourceChartRef,
    VersionChartRef,
)
from zep_dev.development_environments.local_charts import LocalChartRef
from zep_dev.development_environments.target import (
    ExecutionTarget,
    execution_target,
)


def test_supporting_only_create_uses_own_target_without_distribution(
    state_home: Path,
    prepare_kind: PrepareKind,
    prepare_kubectl: Callable[[], FakeExecute],
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> None:
    template = write_template(basic_template)
    kind_calls = prepare_kind()
    kubectl_calls = prepare_kubectl()
    target = lifecycle.create_environment(template)
    assert target == execution_target(
        "integration", environ={"XDG_STATE_HOME": str(state_home)}
    )
    assert target.kubeconfig.read_text() == "targeted kubeconfig"
    assert len(kind_calls.calls_for("kind", "create")) == 1
    assert any(
        "--context=kind-zep-dev-integration" in call.args
        for call in kubectl_calls.calls
    )
    assert any(
        call.args[3:5] == ("create", "namespace") for call in kubectl_calls.calls
    )


def test_preflight_error_precedes_kind_and_owned_directory(
    state_home: Path,
    prepare_kind: PrepareKind,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> None:
    basic_template["cluster"]["mounts"] = [{"slot": "data", "node_path": "/data"}]
    basic_template["inputs"] = {"mounts": ["data"]}
    template = write_template(basic_template)
    calls = prepare_kind()
    with pytest.raises(FileNotFoundError, match="Bindings not found"):
        lifecycle.create_environment(template)
    assert calls.calls == []
    assert not execution_target("integration").directory.exists()


def test_helm_service_is_installed_with_own_namespace(
    state_home: Path,
    prepare_kind: PrepareKind,
    prepare_kubectl: Callable[[], FakeExecute],
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    fake_execute: FakeExecuteFactory,
) -> None:
    basic_template["services"] = {
        "operator": {
            "type": "helm",
            "namespace": "operators",
            "chart": "cloudnative-pg",
            "repository": "https://example.org/charts",
            "version": "1.0.0",
        }
    }
    prepare_kind()
    prepare_kubectl()
    helm_calls = (
        fake_execute(helm).on("helm", "list", stdout="[]").on("helm", "install")
    )
    lifecycle.create_environment(write_template(basic_template))
    [install] = helm_calls.calls_for("helm", "install")
    _, _, release, chart, *_options = install.args
    assert (release, chart) == ("operator", "cloudnative-pg")
    assert option_value(install.args, "--namespace") == "operators"
    assert option_value(install.args, "--repo") == "https://example.org/charts"


def test_chart_refs_are_checked_once_and_passed_to_install(
    write_distribution: WriteDistribution,
    chart_resolver: RecordingChartResolver,
    registry_auth: Path,
    state_home: Path,
    prepare_kind: PrepareKind,
    prepare_kubectl: Callable[[], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> None:
    distribution = write_distribution(eas={"version": "1.0.0"})
    basic_template["distribution"] = distribution.name
    template = write_template(basic_template)
    ref = VersionChartRef(name="eas", version="1.0.0", source="version")
    events: list[str] = []

    chart_resolver.refs = [ref]

    monkeypatch.setattr(
        secrets,
        "create_image_pull_secret",
        lambda *_args: events.append("pull-secret"),
    )

    def install(
        _target: ExecutionTarget,
        refs: Sequence[ChartRef],
        _values: dict[str, dict[str, Any]],
    ) -> None:
        assert refs == (ref,)
        events.append("install")

    monkeypatch.setattr(helm, "install_applications", install)
    prepare_kind()
    prepare_kubectl()
    lifecycle.create_environment(template)
    assert events == ["pull-secret", "install"]
    assert len(chart_resolver.resolutions) == 1
    assert chart_resolver.checked == [ref]


def test_two_environment_names_use_distinct_clusters_and_files(
    state_home: Path,
    prepare_kubectl: Callable[[], FakeExecute],
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    fake_execute: FakeExecuteFactory,
) -> None:
    names: list[str] = []

    def write_config(args: tuple[str, ...], _kwargs: dict[str, object]) -> None:
        path = Path(args[args.index("--kubeconfig") + 1])
        path.write_text(args[args.index("--name") + 1])
        names.append(path.read_text())

    calls = (
        fake_execute(kind)
        .on("kind", "get", "clusters", "--quiet", stdout="")
        .on("kind", "create", "cluster", hook=write_config)
    )
    prepare_kubectl()
    targets = []
    for name in ("first", "second"):
        basic_template["metadata"]["name"] = name
        targets.append(lifecycle.create_environment(write_template(basic_template)))
    assert names == ["zep-dev-first", "zep-dev-second"]
    first, second = targets
    assert first.directory != second.directory
    assert first.kubeconfig.read_text() == "zep-dev-first"
    assert second.kubeconfig.read_text() == "zep-dev-second"
    assert len(calls.calls_for("kind", "create")) == 2


def test_reuse_without_runtime_state_still_attempts_database_apply(
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    write_distribution: WriteDistribution,
    chart_resolver: RecordingChartResolver,
    registry_auth: Path,
    state_home: Path,
    prepare_kind: PrepareKind,
    prepare_kubectl: Callable[[], FakeExecute],
    monkeypatch: pytest.MonkeyPatch,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> None:
    write_distribution(hcs={"local": True})
    basic_template.update(
        {
            "distribution": "dist.yaml",
            "services": {
                "database": {
                    "type": "cnpg",
                    "database": "hcs",
                    "owner": "hcs",
                    "password": "development",
                    "spec": {},
                }
            },
            "applications": {
                "hcs": {
                    "databases": {"primary": {"service": "database", "database": "hcs"}}
                }
            },
        }
    )
    checkout = tmp_path / "hosting-capacity-service"
    wrapper = checkout / "helm/charts/hcs/kind-runtime-contract"
    wrapper.mkdir(parents=True)
    chart_resolver.refs = [
        LocalChartRef(
            name="hcs", version="1.0.0", repo=checkout, package=tmp_path / "hcs.tgz"
        )
    ]

    monkeypatch.setattr(cnpg, "apply_cnpg_service", lambda *_args: None)
    monkeypatch.setattr(helm, "install_applications", lambda *_args: None)
    runtime_root = execution_target("integration").runtime_root
    terraform_calls = (
        fake_execute(terraform)
        .on("terraform", f"-chdir={runtime_root}", "init")
        .on("terraform", f"-chdir={runtime_root}", "apply")
    )
    calls = prepare_kind(present=True)
    prepare_kubectl()
    lifecycle.create_environment(write_template(basic_template), allow_reuse=True)
    [apply] = terraform_calls.calls_for("terraform", f"-chdir={runtime_root}", "apply")
    assert f"-state={runtime_root / 'terraform.tfstate'}" in apply.args
    config = json.loads((runtime_root / "main.tf.json").read_text())
    source = config["module"]["hcs_runtime_contract"]["source"]
    assert (runtime_root / source).resolve() == wrapper
    assert len(calls.calls_for("kind", "export")) == 1


def test_missing_image_archive_is_refused_before_kind(
    state_home: Path,
    prepare_kind: PrepareKind,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    tmp_path: Path,
) -> None:
    calls = prepare_kind()
    with pytest.raises(ZepDevError, match="image archive is missing or empty"):
        lifecycle.create_environment(
            write_template(basic_template), image_archive=tmp_path / "images.tar"
        )
    assert calls.calls == []


@pytest.fixture
def local_eas_template(
    write_distribution: WriteDistribution,
    chart_resolver: RecordingChartResolver,
    registry_auth: Path,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    tmp_path: Path,
) -> tuple[Path, Path]:
    """A Template whose EAS, with a database, comes from a local checkout."""
    write_distribution(eas={"local": True})
    basic_template.update(
        {
            "distribution": "dist.yaml",
            "services": {
                "database": {
                    "type": "cnpg",
                    "database": "eas",
                    "owner": "eas",
                    "password": "development",
                    "spec": {},
                }
            },
            "applications": {
                "eas": {
                    "databases": {"primary": {"service": "database", "database": "eas"}}
                }
            },
        }
    )
    checkout = tmp_path / "evolve-app-server"
    chart_resolver.refs = [
        LocalChartRef(
            name="eas", version="1.0.0", repo=checkout, package=tmp_path / "eas.tgz"
        )
    ]
    return write_template(basic_template), checkout


def test_local_chart_supplies_its_own_kind_wrapper(
    local_eas_template: tuple[Path, Path],
) -> None:
    template, checkout = local_eas_template
    wrapper = checkout / "helm/charts/eas/kind-runtime-contract"
    wrapper.mkdir(parents=True)

    [application] = lifecycle.preflight(template).runtime_applications

    assert application.module == wrapper


def test_databases_without_a_kind_wrapper_are_refused_in_preflight(
    local_eas_template: tuple[Path, Path],
) -> None:
    template, _checkout = local_eas_template

    with pytest.raises(ZepDevError, match="no Kind wrapper was found for eas"):
        lifecycle.preflight(template)


@pytest.mark.parametrize("has_wrapper", [True, False], ids=["wrapper", "no-wrapper"])
def test_kind_wrapper_is_applied_whenever_the_chart_revision_has_one(
    write_distribution: WriteDistribution,
    chart_resolver: RecordingChartResolver,
    registry_auth: Path,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    tmp_path: Path,
    has_wrapper: bool,
) -> None:
    write_distribution(eas={"local": True})
    basic_template.update(
        {"distribution": "dist.yaml", "applications": {"eas": {"values": {"a": 1}}}}
    )
    checkout = tmp_path / "evolve-app-server"
    wrapper = checkout / "helm/charts/eas/kind-runtime-contract"
    if has_wrapper:
        wrapper.mkdir(parents=True)
    chart_resolver.refs = [
        LocalChartRef(
            name="eas", version="1.0.0", repo=checkout, package=tmp_path / "eas.tgz"
        )
    ]

    plan = lifecycle.preflight(write_template(basic_template))

    expected = (
        (terraform.RuntimeApplication("eas", {}, wrapper),) if has_wrapper else ()
    )
    assert plan.runtime_applications == expected


def test_missing_source_chart_is_refused_without_build_or_cluster_mutation(
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
    write_distribution: WriteDistribution,
    prepare_kind: PrepareKind,
    fake_execute: FakeExecuteFactory,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    sha = "a" * 40
    distribution = write_distribution(eas={"commit": sha})
    basic_template["distribution"] = distribution.name
    ref = SourceChartRef(
        name="eas",
        version="snapshot",
        source="commit",
        sha=sha,
        repo_name="evolve-app-server",
        repo=tmp_path,
    )
    monkeypatch.setattr(
        chart_sources.ChartResolver, "resolve_all", lambda _self, _charts: [ref]
    )
    ensure = Mock(side_effect=AssertionError("creation requested a build"))
    monkeypatch.setattr(chart_sources.ChartResolver, "ensure", ensure)
    probe = fake_execute(chart_sources).on(
        "helm", "pull", returncode=1, stderr="manifest unknown"
    )
    cluster = prepare_kind()
    with pytest.raises(FileNotFoundError, match="run distribution build first"):
        lifecycle.create_environment(write_template(basic_template))
    ensure.assert_not_called()
    assert len(probe.calls) == 1
    assert cluster.calls == []
    assert not execution_target("integration").directory.exists()
