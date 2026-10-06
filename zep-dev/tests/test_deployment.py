import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml
from pydantic import TypeAdapter

from _fake_execute import FakeExecuteFactory
from zep_dev import chart_artifacts, cluster, deployment, terraform_roots
from zep_dev.chart_artifacts import ChartRef, ChartResolver
from zep_dev.commands.deployment import destroy as destroy_cmd
from zep_dev.profile import Profile

WriteProfile = Callable[..., Path]


def test_deployment_destroy_deletes_cluster_named_in_profile_metadata(
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        "metadata:\n  name: with-load-db\ndistribution: missing.yaml\n",
        encoding="utf-8",
    )
    destroyed: list[str] = []
    monkeypatch.setattr(
        destroy_cmd, "discard_profile_terraform", lambda name: destroyed.append(name)
    )
    fake = fake_execute(cluster).on(
        "kind",
        "delete",
        "cluster",
        hook=lambda args, kwargs: destroyed.append("cluster"),
    )

    assert destroy_cmd.destroy.callback is not None
    destroy_cmd.destroy.callback(profile)

    assert destroyed == ["cluster", "with-load-db"]
    args = fake.calls_for("kind", "delete", "cluster")[0].args
    assert args[args.index("--name") + 1] == "with-load-db"


def test_preflight_requires_bindings_when_profile_has_slots(
    write_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_profile(
        body={
            "k8s": {
                "mounts": [{"slot": "ewb-data", "node_path": "/mnt/ewb-data"}],
            }
        }
    )
    loaded = Profile.from_path(path)
    monkeypatch.chdir(path.parent)
    monkeypatch.delenv("ZEP_DEV_BINDINGS", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(path.parent / "empty-config"))
    monkeypatch.setattr(ChartResolver, "check_all", lambda self, refs: None)
    monkeypatch.setattr(
        deployment, "resolve_registry_credential", lambda registry: ("u", "p")
    )

    with pytest.raises(FileNotFoundError, match="Bindings not found"):
        deployment.preflight(loaded)


def test_preflight_requires_oci_chart_before_kind_mutation(
    write_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = Profile.from_path(write_profile(ewb={"version": "1.0.0"}))

    def fail_check(self: ChartResolver, refs: list[ChartRef]) -> None:
        raise FileNotFoundError("Missing OCI chart for ewb:1.0.0")

    monkeypatch.setattr(ChartResolver, "check_all", fail_check)
    monkeypatch.setattr(
        deployment,
        "ensure_kind_cluster",
        lambda *args, **kwargs: pytest.fail("Kind started"),
    )

    with pytest.raises(FileNotFoundError, match="Missing OCI chart"):
        deployment.apply_deployment(loaded)


def test_source_chart_miss_stops_apply_before_kind(
    write_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = Profile.from_path(write_profile(ewb={"pullRequest": 42}))

    def resolve(self: ChartResolver, name: str, loc: object) -> ChartRef:
        return ChartRef(
            name=name,  # type: ignore[arg-type]
            version="1.2.3",
            source="pullRequest",
            sha="a" * 40,
            repo_name="energy-workbench-server",
            repo=Path("/tmp/repo"),
        )

    monkeypatch.setattr(ChartResolver, "resolve", resolve)
    monkeypatch.setattr(chart_artifacts, "probe_oci_chart", lambda *args, **kw: False)
    monkeypatch.setattr(
        deployment,
        "ensure_kind_cluster",
        lambda *args, **kwargs: pytest.fail("Kind started"),
    )

    with pytest.raises(FileNotFoundError, match="run distribution build first"):
        deployment.apply_deployment(loaded)


def test_install_distribution_apps_installs_each_with_wait_and_values(
    write_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = {
        "chart": "value-chart",
        "version": "value-version",
        "repository": "value-repository",
    }
    path = write_profile(
        ewb={"version": "1.0.0"},
        hcs={"version": "2.0.0"},
        body={"apps": {"ewb": values}},
    )
    loaded = Profile.from_path(path)
    refs = [
        ChartRef(name="ewb", version="1.0.0", source="version"),
        ChartRef(name="hcs", version="2.0.0", source="version"),
    ]
    overlays = []
    calls: list[list[str]] = []

    def start_helm(
        args: list[str],
        *,
        stdout: int,
        stderr: int,
        encoding: str,
        errors: str,
        start_new_session: bool,
    ) -> Mock:
        assert stdout == stderr == subprocess.PIPE
        assert encoding == "utf-8" and errors == "replace" and start_new_session
        calls.append(args)
        if "-f" in args:
            overlays.append(
                yaml.safe_load(Path(args[args.index("-f") + 1]).read_text())
            )
        return Mock(
            args=args,
            returncode=0,
            communicate=Mock(
                side_effect=[
                    subprocess.TimeoutExpired(args, 0.1),
                    ("Helm install completed\n", "Helm warning\n"),
                ]
            ),
        )

    monkeypatch.setattr(deployment, "resolve", lambda name: None)
    monkeypatch.setattr(deployment.subprocess, "Popen", start_helm)

    deployment.install_distribution_apps(loaded, refs)

    assert len(calls) == 2
    ewb_args = next(args for args in calls if "ewb" in args)
    assert "--wait" in ewb_args
    assert "--rollback-on-failure" in ewb_args
    assert f"--timeout={deployment.APP_HELM_TIMEOUT}" in ewb_args
    assert "-f" in ewb_args

    assert ewb_args[:5] == [
        "helm",
        "upgrade",
        "--install",
        "ewb",
        "oci://ghcr.io/zepben/charts/ewb",
    ]
    assert ewb_args[ewb_args.index("--version") + 1] == "1.0.0"
    assert overlays == [values]
    output = capsys.readouterr()
    assert output.out.count("Helm install completed") == 2
    assert output.err.count("Helm warning") == 2


def test_apply_deployment_runs_terraform_before_apps(
    contract_profile: Profile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    monkeypatch.setattr(
        deployment,
        "preflight",
        lambda p: deployment.PreflightResult([], [], Path("/deployments")),
    )
    monkeypatch.setattr(
        deployment,
        "ensure_kind_cluster",
        lambda p, *, allow_reuse, host_mounts=(): order.append("kind"),
    )
    monkeypatch.setattr(cluster, "apply_builtin_storage_classes", lambda: None)
    monkeypatch.setattr(cluster, "add_helm_repos", lambda h: None)
    monkeypatch.setattr(
        cluster,
        "install_helm_components",
        lambda h, *, source_dir: order.append("k8s"),
    )
    monkeypatch.setattr(deployment, "resource_exists", lambda *args, **kwargs: True)
    monkeypatch.setattr(deployment, "create_image_pull_secret", lambda ns: None)
    monkeypatch.setattr(deployment, "apply_deployment_secrets", lambda p: None)
    monkeypatch.setattr(
        deployment, "apply_runtime_manifests", lambda p: order.append("manifests")
    )
    monkeypatch.setattr(
        deployment, "apply_deployment_terraform", lambda p, d: order.append("terraform")
    )
    monkeypatch.setattr(
        deployment,
        "install_distribution_apps",
        lambda p, refs=None: order.append("apps"),
    )

    deployment.apply_deployment(contract_profile)
    assert order == ["kind", "k8s", "terraform", "manifests", "apps"]


def test_resolve_version_charts() -> None:
    from zep_dev.distribution import Charts

    refs = ChartResolver().resolve_all(
        TypeAdapter(Charts).validate_python(
            {"ewb": {"version": "1.0.0"}, "eas": {"version": "2.0.0"}}
        )
    )
    assert [ref.label() for ref in refs] == ["ewb:1.0.0", "eas:2.0.0"]


def test_ensure_kind_cluster_fails_if_exists_without_allow_reuse(
    write_profile: WriteProfile,
    fake_execute: FakeExecuteFactory,
) -> None:
    loaded = Profile.from_path(write_profile(name="demo"))
    fake = fake_execute(cluster).on("kind", "get", "clusters", stdout="demo\n")

    with pytest.raises(RuntimeError, match="already exists"):
        deployment.ensure_kind_cluster(loaded, allow_reuse=False)

    assert fake.calls_for("kind", "create") == []


def test_destroy_failure_preserves_profile_files(
    tmp_path: Path, generated_tf_base: Path, fake_execute: FakeExecuteFactory
) -> None:
    root = terraform_roots.profile_tf_dir("demo")
    root.mkdir(parents=True)
    state = root / "terraform.tfstate"
    state.write_text("{}")
    profile = tmp_path / "profile.yaml"
    profile.write_text("metadata: {name: demo}\n")
    fake_execute(cluster).on(
        "kind", "delete", "cluster", raises=subprocess.CalledProcessError(1, ["kind"])
    )
    assert destroy_cmd.destroy.callback is not None
    with pytest.raises(subprocess.CalledProcessError):
        destroy_cmd.destroy.callback(profile)
    assert state.is_file()


def test_apply_uses_one_state_even_after_all_databases_removed(
    write_profile: WriteProfile,
    generated_tf_base: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = Profile.from_path(write_profile())
    root = terraform_roots.profile_tf_dir("demo")
    root.mkdir(parents=True)
    state = root / "terraform.tfstate"
    state.write_text("{}")
    calls: list[tuple[Path, str, Path]] = []
    monkeypatch.setattr(
        deployment,
        "apply_terraform",
        lambda root, namespace, *, state: calls.append((root, namespace, state)),
    )
    deployment.apply_deployment_terraform(profile, None)
    assert calls == [(root, "integration", state)]
    assert json.loads((root / "main.tf.json").read_text())["module"] == {}
