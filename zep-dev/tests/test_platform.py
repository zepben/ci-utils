"""Tests for platform destroy/apply.

No live Kind/OCI: subprocesses are faked. Schema rules stay in
test_distribution.py.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import pytest
import yaml
from click.testing import CliRunner

from _fake_execute import FakeExecuteFactory
from zep_dev import cluster, cnpg, platform
from zep_dev.cli import cli
from zep_dev.cluster import CLUSTER_NAME
from zep_dev.distribution import Components, Profile
from zep_dev.models import HostMount
from zep_dev.shared import CommandResult

WriteProfile = Callable[..., Path]


@pytest.fixture
def write_apply_profile(tmp_path: Path) -> WriteProfile:
    def _write(
        *,
        name: str = "demo",
        body: dict[str, Any] | None = None,
        **components: dict[str, object],
    ) -> Path:
        dist = {
            "metadata": {"name": "platform-draft"},
            "components": components or {"ewb": {"version": "1.0.0"}},
        }
        (tmp_path / "dist.yaml").write_text(
            yaml.safe_dump(dist, sort_keys=False), encoding="utf-8"
        )
        profile: dict[str, Any] = {
            "metadata": {"name": name},
            "distribution": "dist.yaml",
            "namespace": "platform",
            "kind": {
                "config": {
                    "kind": "Cluster",
                    "apiVersion": "kind.x-k8s.io/v1alpha4",
                    "nodes": [],
                }
            },
        }
        if body:
            profile.update(body)
        path = tmp_path / "profile.yaml"
        path.write_text(yaml.safe_dump(profile, sort_keys=False), encoding="utf-8")
        return path

    return _write


# --- destroy -----------------------------------------------------------------


def test_platform_destroy_deletes_cluster_named_in_profile_metadata(
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zep_dev.commands.platform import destroy as destroy_cmd

    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """\
metadata:
  name: with-load-db
distribution: does-not-exist.yaml
unknown_for_full_load: true
""",
        encoding="utf-8",
    )
    destroyed: list[str] = []
    monkeypatch.setattr(
        destroy_cmd, "destroy_profile_terraform", lambda name: destroyed.append(name)
    )
    fake = fake_execute(cluster).on("kind", "delete", "cluster")

    assert destroy_cmd.destroy.callback is not None
    destroy_cmd.destroy.callback(profile)

    assert destroyed == ["with-load-db"]
    assert fake.calls_for("kind", "delete", "cluster")[0].args == (
        "kind",
        "delete",
        "cluster",
        "--name",
        "with-load-db",
    )


def test_platform_destroy_rejects_reserved_cluster_name(
    tmp_path: Path,
    fake_execute: FakeExecuteFactory,
) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        f"""\
metadata:
  name: {CLUSTER_NAME}
""",
        encoding="utf-8",
    )
    fake = fake_execute(cluster)

    result = CliRunner().invoke(cli, ["platform", "destroy", "--profile", str(profile)])

    assert result.exit_code != 0
    assert fake.calls_for("kind") == []


# --- apply -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("locator", "source_kind"),
    [({"pullRequest": 42}, "pullRequest"), ({"commit": "a" * 40}, "commit")],
)
def test_install_refs_resolves_pr_and_commit_from_source(
    locator: dict[str, object],
    source_kind: Literal["pullRequest", "commit"],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = Components.model_validate({"ewb": locator})
    resolved: list[str] = []

    def resolve(
        name: str, locator: object, cache: object, api: object
    ) -> tuple[Path, str, str]:
        resolved.append(name)
        return Path("/tmp/repo"), "a" * 40, "1.2.3"

    monkeypatch.setattr(platform, "resolve_source_chart", resolve)

    assert platform.install_refs(components) == [
        platform.InstallRef(
            "ewb", "oci://ghcr.io/zepben/charts/ewb", "1.2.3", source_kind
        )
    ]
    assert resolved == ["ewb"]


def test_install_refs_resolves_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    components = Components.model_validate(
        {"ewb": {"version": "1.0.0"}, "eas": {"version": "2.0.0"}}
    )

    assert platform.install_refs(components) == [
        platform.InstallRef(
            "ewb", "oci://ghcr.io/zepben/charts/ewb", "1.0.0", "version"
        ),
        platform.InstallRef(
            "eas", "oci://ghcr.io/zepben/charts/eas", "2.0.0", "version"
        ),
    ]


def test_install_refs_reuses_git_cache_for_multiple_source_locators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    components = Components.model_validate(
        {"ewb": {"pullRequest": 1}, "eas": {"commit": "a" * 40}}
    )
    constructed: list[str] = []

    class CountingCache:
        def __init__(self) -> None:
            constructed.append("cache")

    class CountingAPI:
        def __init__(self) -> None:
            constructed.append("api")

    def resolve(
        name: str, locator: object, cache: object, api: object
    ) -> tuple[Path, str, str]:
        return Path("/tmp/repo"), "a" * 40, f"{name}-1.0.0"

    monkeypatch.setattr(platform, "GitCache", CountingCache)
    monkeypatch.setattr(platform, "GitHubAPI", CountingAPI)
    monkeypatch.setattr(platform, "resolve_source_chart", resolve)

    refs = platform.install_refs(components)

    assert [ref.version for ref in refs] == ["ewb-1.0.0", "eas-1.0.0"]
    assert constructed == ["cache", "api"]


def test_profile_rejects_external_kind_config(
    write_apply_profile: WriteProfile,
) -> None:
    path = write_apply_profile(body={"kind": {"config": "kind-cluster.yaml"}})

    with pytest.raises(ValueError, match="kind.config"):
        Profile.from_path(path)


def test_check_oci_charts_fails_clearly_when_missing(
    write_apply_profile: WriteProfile,
    fake_execute: FakeExecuteFactory,
) -> None:
    fake_execute(cluster).on(
        "helm",
        "show",
        "chart",
        returncode=1,
        stderr="Error: manifest unknown",
    )

    with pytest.raises(FileNotFoundError, match="OCI not-found"):
        platform.check_install_artifacts(
            [
                platform.InstallRef(
                    "ewb", "oci://ghcr.io/zepben/charts/ewb", "9.9.9", "version"
                )
            ]
        )


def test_ensure_kind_cluster_fails_if_exists_without_allow_reuse(
    write_apply_profile: WriteProfile,
    fake_execute: FakeExecuteFactory,
) -> None:
    loaded = Profile.from_path(write_apply_profile(name="demo"))
    fake = fake_execute(cluster).on("kind", "get", "clusters", stdout="demo\n")

    with pytest.raises(RuntimeError, match="already exists"):
        platform.ensure_kind_cluster(loaded, allow_reuse=False)

    assert fake.calls_for("kind", "create") == []


def test_create_kind_cluster_exports_kubeconfig_when_reusing(
    fake_execute: FakeExecuteFactory,
    tmp_path: Path,
) -> None:
    kind_config = tmp_path / "kind.yaml"
    kind_config.write_text(
        "kind: Cluster\napiVersion: kind.x-k8s.io/v1alpha4\nnodes: []\n",
        encoding="utf-8",
    )
    fake = (
        fake_execute(cluster)
        .on("kind", "get", "clusters", stdout=f"{CLUSTER_NAME}\n")
        .on("kind", "export", "kubeconfig")
    )

    cluster.create_kind_cluster(kind_config)

    assert fake.calls_for("kind", "create") == []
    assert fake.calls_for("kind", "export", "kubeconfig")


@pytest.mark.parametrize("inline", [False, True], ids=["path", "inline"])
def test_inject_host_mounts_adds_worker_extra_mounts(
    tmp_path: Path, inline: bool
) -> None:
    kind_config = tmp_path / "kind.yaml"
    kind_config.write_text(
        """\
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
""",
        encoding="utf-8",
    )
    mapping = yaml.safe_load(kind_config.read_text(encoding="utf-8"))
    source = mapping if inline else kind_config
    data_dir = tmp_path / "ewb-data"
    data_dir.mkdir()

    rendered = cluster.inject_host_mounts(
        source,
        [
            HostMount(
                host_path=data_dir,
                node_path="/mnt/ewb-data",
                read_only=False,
            )
        ],
    )
    parsed = yaml.safe_load(rendered)
    workers = [n for n in parsed["nodes"] if n["role"] == "worker"]
    assert workers[0]["extraMounts"] == [
        {
            "hostPath": str(data_dir),
            "containerPath": "/mnt/ewb-data",
            "readOnly": False,
        }
    ]
    control = next(n for n in parsed["nodes"] if n["role"] == "control-plane")
    assert "extraMounts" not in control
    assert "extraMounts" not in next(
        n for n in mapping["nodes"] if n["role"] == "worker"
    )


@pytest.mark.parametrize(
    ("nodes", "message"),
    [
        (None, "nodes must be a list"),
        ({"role": "worker"}, "nodes must be a list"),
        ([None], r"nodes\[0\] must be a mapping"),
        (
            [{"role": "worker", "extraMounts": None}],
            r"nodes\[0\]\.extraMounts must be a list",
        ),
    ],
)
def test_inject_host_mounts_rejects_invalid_node_shapes(
    nodes: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        cluster.inject_host_mounts({"kind": "Cluster", "nodes": nodes}, ())


def test_resolved_host_mounts_requires_binding_directories(
    write_apply_profile: WriteProfile,
) -> None:
    from zep_dev.bindings import Bindings

    path = write_apply_profile()
    path.write_text(
        yaml.safe_dump(
            {
                **yaml.safe_load(path.read_text(encoding="utf-8")),
                "kind": {
                    "config": {
                        "kind": "Cluster",
                        "apiVersion": "kind.x-k8s.io/v1alpha4",
                        "nodes": [],
                    },
                    "host_mounts": [
                        {
                            "slot": "ewb-data",
                            "node_path": "/mnt/ewb-data",
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loaded = Profile.from_path(path)
    bindings = Bindings(mounts={"ewb-data": path.parent / "missing-ewb-data"})

    with pytest.raises(ValueError, match="bindings.mounts.ewb-data"):
        loaded.resolved_host_mounts(bindings)


def test_preflight_requires_bindings_when_profile_has_slots(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_apply_profile(
        body={
            "kind": {
                "config": {
                    "kind": "Cluster",
                    "apiVersion": "kind.x-k8s.io/v1alpha4",
                    "nodes": [],
                },
                "host_mounts": [{"slot": "ewb-data", "node_path": "/mnt/ewb-data"}],
            }
        }
    )
    loaded = Profile.from_path(path)
    monkeypatch.delenv("ZEP_DEV_BINDINGS", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(path.parent / "empty-config"))
    monkeypatch.setattr(platform, "check_oci_chart", lambda *args: None)
    monkeypatch.setattr(
        platform, "resolve_registry_credential", lambda registry: ("u", "p")
    )

    with pytest.raises(FileNotFoundError, match="Bindings not found"):
        platform.preflight(loaded)


def test_ensure_kind_cluster_passes_resolved_host_mounts(
    write_apply_profile: WriteProfile,
    fake_execute: FakeExecuteFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_apply_profile()
    data_dir = path.parent / "ewb-data"
    data_dir.mkdir()
    path.write_text(
        yaml.safe_dump(
            {
                **yaml.safe_load(path.read_text(encoding="utf-8")),
                "kind": {
                    "config": {
                        "kind": "Cluster",
                        "apiVersion": "kind.x-k8s.io/v1alpha4",
                        "nodes": [],
                    },
                    "host_mounts": [
                        {
                            "slot": "ewb-data",
                            "node_path": "/mnt/ewb-data",
                        }
                    ],
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loaded = Profile.from_path(path)
    from zep_dev.bindings import Bindings
    from zep_dev.models import HostMount

    mounts = loaded.resolved_host_mounts(Bindings(mounts={"ewb-data": data_dir}))
    captured: dict[str, object] = {}

    def fake_create(
        kind_config: Path | dict[str, Any],
        local_repos: object = (),
        *,
        host_mounts: object = (),
        cluster_name: str = CLUSTER_NAME,
    ) -> None:
        captured["host_mounts"] = host_mounts
        captured["cluster_name"] = cluster_name

    monkeypatch.setattr(cluster, "create_kind_cluster", fake_create)
    fake_execute(cluster).on("kind", "get", "clusters", stdout="")

    platform.ensure_kind_cluster(loaded, allow_reuse=False, host_mounts=mounts)

    got = captured["host_mounts"]
    assert isinstance(got, list)
    assert len(got) == 1
    assert isinstance(got[0], HostMount)
    assert got[0].node_path == "/mnt/ewb-data"
    assert got[0].host_path == data_dir.resolve()


def test_install_distribution_apps_installs_each_with_wait_and_values(
    write_apply_profile: WriteProfile,
    fake_execute: FakeExecuteFactory,
) -> None:
    path = write_apply_profile(
        ewb={"version": "1.0.0"},
        hcs={"version": "2.0.0"},
        body={"apps": {"ewb": {"values": {"replicaCount": 1}}}},
    )
    loaded = Profile.from_path(path)
    fake = fake_execute(cluster).on("helm", "upgrade", "--install")

    platform.install_distribution_apps(loaded)

    calls = fake.calls_for("helm", "upgrade", "--install")
    releases = {c.args[3] for c in calls}
    assert releases == {"ewb", "hcs"}
    ewb_args = next(c.args for c in calls if c.args[3] == "ewb")
    assert "oci://ghcr.io/zepben/charts/ewb" in ewb_args
    assert ewb_args[ewb_args.index("--version") + 1] == "1.0.0"
    assert "--wait" in ewb_args
    assert "--timeout=10m" in ewb_args
    assert "-f" in ewb_args


def test_install_distribution_apps_reports_all_failures(
    write_apply_profile: WriteProfile,
    fake_execute: FakeExecuteFactory,
) -> None:
    path = write_apply_profile(
        ewb={"version": "1.0.0"},
        hcs={"version": "2.0.0"},
    )
    loaded = Profile.from_path(path)
    fake_execute(cluster).on(
        "helm",
        "upgrade",
        "--install",
        returncode=1,
        stderr="install failed",
    )

    with pytest.raises(RuntimeError, match="App install failed") as exc_info:
        platform.install_distribution_apps(loaded)

    message = str(exc_info.value)
    assert "ewb:" in message
    assert "hcs:" in message


def test_apply_profile_secrets_creates_from_profile(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_apply_profile(
        body={
            "secrets": [
                {"name": "ewb-ci-aws-credentials", "env_var": "CI_SECRET_ENV"},
            ],
        },
    )
    monkeypatch.setenv(
        "CI_SECRET_ENV", "AWS_ACCESS_KEY_ID=x\nAWS_SECRET_ACCESS_KEY=y\n"
    )
    loaded = Profile.from_path(path)
    calls: list[tuple[tuple[str, ...], str | None]] = []

    def fake_resource_exists(
        kind: str, name: str, namespace: str | None = None
    ) -> bool:
        return False

    def fake_kubectl(*args: str, input: str | None = None, **kwargs: object) -> None:
        calls.append((args, input))

    monkeypatch.setattr(platform, "resource_exists", fake_resource_exists)
    monkeypatch.setattr(platform, "kubectl", fake_kubectl)

    platform.apply_profile_secrets(loaded)

    assert len(calls) == 1
    assert calls[0][0][:5] == (
        "--namespace=platform",
        "create",
        "secret",
        "generic",
        "ewb-ci-aws-credentials",
    )
    assert calls[0][1] is not None
    assert "AWS_ACCESS_KEY_ID=x" in calls[0][1]


def test_apply_profile_secrets_noop_when_empty(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = Profile.from_path(write_apply_profile())
    calls: list[tuple[str, ...]] = []

    def fake_kubectl(*args: str, **kwargs: object) -> None:
        calls.append(args)

    monkeypatch.setattr(platform, "kubectl", fake_kubectl)

    platform.apply_profile_secrets(loaded)

    assert calls == []


def test_preflight_requires_oci_chart_before_kind_mutation(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = Profile.from_path(write_apply_profile(ewb={"version": "1.0.0"}))
    credentials: list[str] = []
    monkeypatch.setattr(
        platform,
        "resolve_registry_credential",
        lambda registry: credentials.append("checked") or ("u", "p"),
    )
    monkeypatch.setattr(
        platform,
        "check_oci_chart",
        lambda name, version: (_ for _ in ()).throw(
            FileNotFoundError(f"Missing OCI chart for {name}:{version}")
        ),
    )
    monkeypatch.setattr(
        platform,
        "ensure_kind_cluster",
        lambda *args, **kwargs: pytest.fail("Kind started"),
    )

    with pytest.raises(FileNotFoundError, match="Missing OCI chart"):
        platform.apply_profile(loaded)

    assert credentials == []


def test_preflight_checks_version_artifacts_and_oci_credentials(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded = Profile.from_path(
        write_apply_profile(ewb={"version": "1.0.0"}, eas={"version": "2.0.0"})
    )
    checked: list[tuple[str, str]] = []
    credentials: list[str] = []
    monkeypatch.setattr(
        platform,
        "check_oci_chart",
        lambda name, version: checked.append((name, version)),
    )
    monkeypatch.setattr(
        platform,
        "resolve_registry_credential",
        lambda registry: credentials.append("checked") or ("u", "p"),
    )

    refs = platform.preflight(loaded)

    assert refs.refs == platform.install_refs(loaded.distribution.components)
    assert checked == [("ewb", "1.0.0"), ("eas", "2.0.0")]
    assert credentials == ["checked"]


@pytest.mark.parametrize("locator", [{"pullRequest": 42}, {"commit": "a" * 40}])
def test_source_chart_miss_stops_apply_before_kind(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
    locator: dict[str, object],
) -> None:
    loaded = Profile.from_path(write_apply_profile(ewb=locator))
    monkeypatch.setattr(
        platform,
        "resolve_source_chart",
        lambda *args: (Path("/tmp/repo"), "a" * 40, "1.2.3"),
    )
    monkeypatch.setattr(platform, "probe_oci_chart", lambda *args: False)
    monkeypatch.setattr(
        platform,
        "ensure_kind_cluster",
        lambda *args, **kwargs: pytest.fail("Kind started"),
    )

    with pytest.raises(FileNotFoundError, match="run distribution build first"):
        platform.apply_profile(loaded)


def test_source_chart_apply_installs_existing_oci_version(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
    fake_execute: FakeExecuteFactory,
) -> None:
    loaded = Profile.from_path(write_apply_profile(ewb={"pullRequest": 42}))
    monkeypatch.setattr(
        platform,
        "resolve_source_chart",
        lambda *args: (Path("/tmp/repo"), "a" * 40, "1.2.3"),
    )
    checked: list[tuple[str, str]] = []

    def probe(name: str, version: str) -> bool:
        checked.append((name, version))
        return True

    monkeypatch.setattr(platform, "probe_oci_chart", probe)
    monkeypatch.setattr(
        platform, "resolve_registry_credential", lambda registry: ("u", "p")
    )
    refs = platform.preflight(loaded)
    fake = fake_execute(cluster).on("helm", "upgrade", "--install")

    platform.install_distribution_apps(loaded, refs.refs)

    args = fake.calls_for("helm", "upgrade", "--install")[0].args
    assert checked == [("ewb", "1.2.3")]
    assert "oci://ghcr.io/zepben/charts/ewb" in args
    assert args[args.index("--version") + 1] == "1.2.3"
    assert "--wait" in args


def test_profile_rejects_app_chart_path(
    write_apply_profile: WriteProfile,
) -> None:
    path = write_apply_profile(body={"apps": {"ewb": {"chart": "/tmp/ewb"}}})

    with pytest.raises(ValueError, match="Extra inputs are not permitted"):
        Profile.from_path(path)


def test_apply_profile_loads_image_archive_when_provided(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    loaded = Profile.from_path(write_apply_profile(name="demo"))
    archive = tmp_path / "images.tar"
    archive.write_bytes(b"archive")
    loaded_archives: list[tuple[Path, str]] = []

    monkeypatch.setattr(
        platform, "preflight", lambda p: platform.PreflightResult([], [], None)
    )
    monkeypatch.setattr(platform, "ensure_kind_cluster", lambda p, *, allow_reuse, host_mounts=(): None)
    monkeypatch.setattr(cluster, "apply_builtin_storage_classes", lambda: None)
    monkeypatch.setattr(cluster, "add_helm_repos", lambda h: None)
    monkeypatch.setattr(cluster, "install_helm_components", lambda h: None)
    monkeypatch.setattr(platform, "resource_exists", lambda *args, **kwargs: True)
    monkeypatch.setattr(platform, "create_image_pull_secret", lambda ns: None)
    monkeypatch.setattr(platform, "apply_profile_secrets", lambda p: None)
    monkeypatch.setattr(
        platform, "apply_profile_terraform", lambda p, deployments_root: None
    )
    monkeypatch.setattr(
        platform, "install_distribution_apps", lambda p, refs=None: None
    )
    monkeypatch.setattr(
        cluster,
        "load_image_archive",
        lambda path, *, cluster_name: loaded_archives.append((path, cluster_name)),
    )

    platform.apply_profile(loaded)
    assert loaded_archives == []

    platform.apply_profile(loaded, image_archive=archive)
    assert loaded_archives == [(archive, "demo")]


def test_apply_profile_runs_terraform_before_apps(
    write_apply_profile: WriteProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_apply_profile()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["terraform"] = {
        "contracts": ["eas"],
    }
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    loaded = Profile.from_path(path)
    order: list[str] = []

    monkeypatch.setattr(
        platform,
        "preflight",
        lambda p: platform.PreflightResult([], [], Path("/deployments")),
    )
    monkeypatch.setattr(
        platform,
        "ensure_kind_cluster",
        lambda p, *, allow_reuse, host_mounts=(): order.append("kind"),
    )
    monkeypatch.setattr(cluster, "apply_builtin_storage_classes", lambda: None)
    monkeypatch.setattr(cluster, "add_helm_repos", lambda h: None)
    monkeypatch.setattr(
        cluster, "install_helm_components", lambda h: order.append("helpers")
    )

    def fake_resource_exists(
        kind: str, name: str, namespace: str | None = None
    ) -> bool:
        return True

    monkeypatch.setattr(platform, "resource_exists", fake_resource_exists)
    monkeypatch.setattr(platform, "create_image_pull_secret", lambda ns: None)
    monkeypatch.setattr(platform, "apply_profile_secrets", lambda p: None)

    def fake_tf(p: Profile, deployments_root: Path) -> None:
        order.append("terraform")

    def fake_apps(p: Profile, refs: object = None) -> None:
        order.append("apps")

    monkeypatch.setattr(platform, "apply_profile_terraform", fake_tf)
    monkeypatch.setattr(platform, "install_distribution_apps", fake_apps)

    platform.apply_profile(loaded)

    assert order == ["kind", "helpers", "terraform", "apps"]


def test_inline_kind_config_passes_directly_to_cluster_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path(__file__).resolve().parents[1]
    profile = Profile.from_path(root / "examples/profiles/platform.yaml")
    created: dict[str, object] = {}

    monkeypatch.setattr(
        cluster, "kind", lambda *args, **kwargs: CommandResult(0, "", "")
    )

    def capture_create(config: Path | dict[str, Any], **kwargs: object) -> None:
        created["config"] = config
        created["name"] = kwargs["cluster_name"]

    monkeypatch.setattr(cluster, "create_kind_cluster", capture_create)
    platform.ensure_kind_cluster(profile, allow_reuse=False, host_mounts=())

    config = created["config"]
    assert config is profile.kind.config
    assert created["name"] == "platform"


def test_cnpg_installer_applies_catalog_before_cluster_and_waits_for_databases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from zep_dev.models import CnpgComponent

    root = Path(__file__).resolve().parents[1]
    profile = Profile.from_path(root / "examples/profiles/platform.yaml")
    hcs = next(
        component
        for component in profile.cluster_components
        if isinstance(component, CnpgComponent) and component.name == "hcs-kind-pg"
    )
    events: list[tuple[str, str]] = []
    manifests: dict[str, list[dict[str, Any]]] = {}
    wait_conditions: list[str] = []

    def capture_kubectl(
        *args: str, input: str | None = None, **kwargs: object
    ) -> CommandResult:
        if args[0] == "apply":
            assert input is not None
            manifest = yaml.safe_load(input)
            manifests.setdefault(manifest["kind"], []).append(manifest)
            events.append(("apply", manifest["kind"]))
            if manifest["kind"] == "Database":
                assert kwargs["capture_stdout"] is True
                assert "-o=json" in args
                return CommandResult(0, json.dumps({"metadata": {"generation": 7}}), "")
        else:
            wait_conditions.append(
                next(arg for arg in args if arg.startswith("--for="))
            )
            events.append(
                (
                    "wait",
                    next(
                        arg for arg in args if arg.startswith(("cluster/", "database/"))
                    ),
                )
            )
        return CommandResult(0, "", "")

    monkeypatch.setattr(cnpg, "kubectl", capture_kubectl)
    cluster.apply_cnpg_component(hcs)

    assert events[:4] == [
        ("apply", "ImageCatalog"),
        ("apply", "Secret"),
        ("apply", "Cluster"),
        ("wait", "cluster/hcs-kind-pg"),
    ]
    catalog = next(iter(manifests["ImageCatalog"]))
    pg_cluster = next(iter(manifests["Cluster"]))
    secret = next(iter(manifests["Secret"]))
    assert hcs.image_catalog is not None
    assert catalog["spec"]["images"] == [
        {"major": 18, "image": hcs.image_catalog.image}
    ]
    assert pg_cluster["spec"]["imageCatalogRef"]["name"] == catalog["metadata"]["name"]
    assert "imageName" not in pg_cluster["spec"]
    assert (
        pg_cluster["spec"]["bootstrap"]["initdb"]["secret"]["name"]
        == secret["metadata"]["name"]
    )
    assert secret["stringData"] == {"username": hcs.owner, "password": hcs.password}
    assert {database["spec"]["name"] for database in manifests["Database"]} == {
        "load",
        "input",
        "results",
    }
    assert all(
        database["spec"]["extensions"] == [{"name": "timescaledb", "ensure": "present"}]
        for database in manifests["Database"]
    )
    assert [event[0] for event in events[4:]] == ["apply", "wait", "wait"] * 3
    assert wait_conditions == ["--for=condition=Ready"] + [
        condition
        for _ in range(3)
        for condition in (
            "--for=jsonpath={.status.observedGeneration}=7",
            "--for=jsonpath={.status.applied}=true",
        )
    ]
