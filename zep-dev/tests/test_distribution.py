"""Tests for Distribution and Profile loading and validation.

We focus on our own rules (aliases, locators, Profile nesting, destroy-time
metadata load). We do not re-test every built-in Pydantic constraint.
"""

from __future__ import annotations

from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from zep_dev.distribution import (
    COMPONENT_LOCATOR_ADAPTER,
    CommitLocator,
    Distribution,
    Profile,
    ProfileMetadata,
    PullRequestLocator,
    VersionLocator,
    load_profile_metadata,
)
from zep_dev.models import LocalManifestComponent

FULL_SHA = "a" * 40

WriteProfile = Callable[..., Path]


@pytest.fixture
def write_distribution(tmp_path: Path) -> Callable[..., Path]:
    def _write(filename: str = "dist.yaml", **components: dict[str, object]) -> Path:
        path = tmp_path / filename
        path.write_text(
            yaml.safe_dump(
                {
                    "metadata": {"name": "platform-latest"},
                    "components": components or {"ewb": {"version": "1.0.0"}},
                },
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        return path

    return _write


@pytest.fixture
def write_profile(
    tmp_path: Path, write_distribution: Callable[..., Path]
) -> WriteProfile:
    def _write(
        *,
        name: str = "demo",
        distribution: str = "dist.yaml",
        body: dict[str, Any] | None = None,
        **components: dict[str, object],
    ) -> Path:
        write_distribution(distribution, **components)
        profile: dict[str, Any] = {
            "metadata": {"name": name},
            "distribution": distribution,
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


# --- Distribution -----------------------------------------------------------


def test_distribution_loads_yaml_including_eas_web_client_alias() -> None:
    distribution = Distribution.from_text_io(
        StringIO(
            """\
metadata:
  name: platform-latest
components:
  ewb:
    version: "2.1.0"
  eas-web-client:
    version: "1.0.0"
"""
        )
    )

    assert distribution.metadata.name == "platform-latest"
    assert distribution.components.ewb == VersionLocator(version="2.1.0")
    assert distribution.components.eas_web_client == VersionLocator(version="1.0.0")
    assert distribution.components.present_keys() == {"ewb", "eas-web-client"}


def test_distribution_requires_at_least_one_component() -> None:
    with pytest.raises(ValidationError, match="at least one"):
        Distribution.model_validate({"metadata": {"name": "x"}, "components": {}})


def test_distribution_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Distribution.model_validate(
            {
                "metadata": {"name": "x"},
                "components": {"ewb": {"version": "1.0.0"}},
                "extra": True,
            }
        )


# --- ComponentLocator -------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        pytest.param(
            {"version": "1.0.0"},
            VersionLocator(version="1.0.0"),
            id="version",
        ),
        pytest.param(
            {"pullRequest": 268},
            PullRequestLocator(pullRequest=268),
            id="pullRequest",
        ),
        pytest.param(
            {"commit": FULL_SHA},
            CommitLocator(commit=FULL_SHA),
            id="commit",
        ),
    ],
)
def test_locator_accepts_exactly_one_kind(
    payload: dict[str, object],
    expected: VersionLocator | PullRequestLocator | CommitLocator,
) -> None:
    assert COMPONENT_LOCATOR_ADAPTER.validate_python(payload) == expected


@pytest.mark.parametrize(
    ("payload", "match"),
    [
        pytest.param({}, r"Field required", id="none"),
        pytest.param(
            {"version": "1.0.0", "pullRequest": 1},
            "Extra inputs are not permitted",
            id="multiple",
        ),
        pytest.param({"branch": "main"}, "Extra inputs are not permitted", id="branch-removed"),
        pytest.param({"version": ""}, "at least 1 character", id="empty-version"),
        pytest.param({"pullRequest": 0}, "greater than 0", id="non-positive-pr"),
        pytest.param(
            {"commit": "abc1234"},
            "at least 40 characters",
            id="abbreviated-commit",
        ),
    ],
)
def test_locator_rejects_invalid(payload: dict[str, object], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        COMPONENT_LOCATOR_ADAPTER.validate_python(payload)


# --- Profile metadata -------------------------------------------------------


def test_profile_metadata_rejects_reserved_cluster_name() -> None:
    with pytest.raises(ValidationError, match="test-cluster"):
        ProfileMetadata.model_validate({"name": "test-cluster"})


@pytest.mark.parametrize(
    "name",
    [
        pytest.param("Invalid_Name", id="underscore"),
        pytest.param("-leading", id="leading-hyphen"),
        pytest.param("a" * 64, id="too-long"),
    ],
)
def test_profile_metadata_rejects_non_dns1123_name(name: str) -> None:
    with pytest.raises(ValidationError):
        ProfileMetadata.model_validate({"name": name})


# --- Profile loader ---------------------------------------------------------


def test_profile_from_path_nests_distribution_and_sets_source_dir(
    tmp_path: Path,
    write_profile: WriteProfile,
) -> None:
    path = write_profile(
        name="with-load-db",
        ewb={"version": "2.1.0"},
        eas={"version": "3.0.0"},
        body={
            "helm_repos": {"cnpg": "https://cloudnative-pg.io/charts/"},
            "cluster_components": [
                {
                    "type": "helm",
                    "name": "cnpg",
                    "chart": "cnpg/cloudnative-pg",
                    "version": "0.28.0",
                    "namespace": "cnpg-system",
                },
                {
                    "type": "local",
                    "name": "eas-pg",
                    "namespace": "platform",
                    "manifests": ["data-plane/eas-pg.yaml"],
                },
            ],
            "apps": {"ewb": {"values": {"loadDatabase": {"enabled": True}}}},
        },
    )

    profile = Profile.from_path(path)

    assert profile.metadata.name == "with-load-db"
    assert profile.distribution.components.ewb == VersionLocator(version="2.1.0")
    assert profile.apps["ewb"].values == {"loadDatabase": {"enabled": True}}
    assert profile.cluster_components[0].type == "helm"
    assert profile.cluster_components[0].name == "cnpg"
    assert profile.cluster_components[1].type == "local"
    assert profile.cluster_components[1].name == "eas-pg"
    assert profile.source_dir == tmp_path.resolve()


def test_profile_rejects_cluster_component_without_type(
    write_profile: WriteProfile,
) -> None:
    path = write_profile(
        body={
            "cluster_components": [
                {
                    "name": "cnpg",
                    "chart": "cnpg/cloudnative-pg",
                    "version": "0.28.0",
                    "namespace": "cnpg-system",
                }
            ],
        },
    )

    with pytest.raises(ValidationError, match="type"):
        Profile.from_path(path)


def test_profile_loads_secrets(write_profile: WriteProfile) -> None:
    path = write_profile(
        ewb={"version": "1.0.0"},
        body={
            "secrets": [
                {"name": "ewb-ci-aws-credentials", "env_var": "CI_SECRET_ENV"},
            ],
        },
    )

    profile = Profile.from_path(path)

    assert len(profile.secrets) == 1
    assert profile.secrets[0].name == "ewb-ci-aws-credentials"
    assert profile.secrets[0].env_var == "CI_SECRET_ENV"


def test_profile_requires_distribution_path(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        """\
metadata:
  name: no-dist
namespace: platform
kind:
  config: {kind: Cluster, apiVersion: kind.x-k8s.io/v1alpha4}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="distribution must be a non-empty path"):
        Profile.from_path(path)


def test_profile_rejects_apps_not_in_distribution(write_profile: WriteProfile) -> None:
    path = write_profile(
        ewb={"version": "1.0.0"},
        body={"apps": {"eas": {"values": {}}}},
    )

    with pytest.raises(ValidationError, match="not in distribution"):
        Profile.from_path(path)


def test_profile_rejects_unknown_app_key(write_profile: WriteProfile) -> None:
    path = write_profile(
        ewb={"version": "1.0.0"},
        body={"apps": {"not-an-app": {"values": {}}}},
    )

    with pytest.raises(ValidationError):
        Profile.from_path(path)


def test_profile_rejects_duplicate_cluster_component_names(
    write_profile: WriteProfile,
) -> None:
    helper = {
        "type": "helm",
        "name": "helper",
        "chart": "example/a",
        "version": "1.0.0",
        "namespace": "platform",
    }
    path = write_profile(
        body={"cluster_components": [helper, {**helper, "chart": "example/b"}]},
    )

    with pytest.raises(ValidationError, match="duplicate cluster_components name"):
        Profile.from_path(path)


def test_profile_rejects_app_and_helper_name_collision(
    write_profile: WriteProfile,
) -> None:
    path = write_profile(
        ewb={"version": "1.0.0"},
        body={
            "cluster_components": [
                {
                    "type": "helm",
                    "name": "ewb",
                    "chart": "example/stub",
                    "version": "1.0.0",
                    "namespace": "platform",
                }
            ]
        },
    )

    with pytest.raises(ValidationError, match="must not collide"):
        Profile.from_path(path)


# --- Destroy path: metadata-only load ---------------------------------------


def test_load_profile_metadata_skips_distribution_and_extra_fields(
    tmp_path: Path,
) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        """\
metadata:
  name: teardown-me
distribution: does-not-exist.yaml
unknown_for_full_load: true
""",
        encoding="utf-8",
    )

    assert load_profile_metadata(path).name == "teardown-me"


def test_load_profile_metadata_requires_metadata(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text("namespace: platform\n", encoding="utf-8")

    with pytest.raises(ValueError, match="missing metadata"):
        load_profile_metadata(path)


def test_profile_resolved_host_mounts_uses_bindings(
    tmp_path: Path,
    write_profile: WriteProfile,
) -> None:
    from zep_dev.bindings import Bindings

    data_dir = tmp_path / "ewb-data"
    data_dir.mkdir()
    path = write_profile(
        body={
            "kind": {
                "config": {"kind": "Cluster", "apiVersion": "kind.x-k8s.io/v1alpha4"},
                "host_mounts": [
                    {
                        "slot": "ewb-data",
                        "node_path": "/mnt/ewb-data",
                    }
                ],
            }
        }
    )
    bindings = Bindings(mounts={"ewb-data": data_dir})

    mounts = Profile.from_path(path).resolved_host_mounts(bindings)

    assert len(mounts) == 1
    assert mounts[0].host_path == data_dir.resolve()
    assert mounts[0].node_path == "/mnt/ewb-data"
    assert mounts[0].read_only is False


def test_profile_resolved_host_mounts_rejects_missing_directory(
    tmp_path: Path,
    write_profile: WriteProfile,
) -> None:
    from zep_dev.bindings import Bindings

    path = write_profile(
        body={
            "kind": {
                "config": {"kind": "Cluster", "apiVersion": "kind.x-k8s.io/v1alpha4"},
                "host_mounts": [
                    {"slot": "ewb-data", "node_path": "/mnt/ewb-data"},
                ],
            }
        }
    )
    bindings = Bindings(mounts={"ewb-data": tmp_path / "missing"})

    with pytest.raises(ValueError, match="bindings.mounts.ewb-data"):
        Profile.from_path(path).resolved_host_mounts(bindings)


def test_profile_rejects_host_path_on_mounts(
    write_profile: WriteProfile,
) -> None:
    path = write_profile(
        body={
            "kind": {
                "config": {"kind": "Cluster", "apiVersion": "kind.x-k8s.io/v1alpha4"},
                "host_mounts": [
                    {
                        "host_path": "/tmp/data",
                        "node_path": "/mnt/ewb-data",
                    }
                ],
            }
        }
    )
    with pytest.raises(ValidationError, match="slot"):
        Profile.from_path(path)


def test_profile_rejects_deployments_root_on_terraform(
    write_profile: WriteProfile,
) -> None:
    path = write_profile(
        body={
            "terraform": {
                "deployments_root": "/tmp/deployments",
                "contracts": ["eas"],
            }
        }
    )
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Profile.from_path(path)


def test_kind_host_mounts_require_unique_slots(
    write_profile: WriteProfile,
) -> None:
    path = write_profile(
        body={
            "kind": {
                "config": {"kind": "Cluster", "apiVersion": "kind.x-k8s.io/v1alpha4"},
                "host_mounts": [
                    {"slot": "ewb-data", "node_path": "/mnt/a"},
                    {"slot": "ewb-data", "node_path": "/mnt/b"},
                ],
            }
        }
    )
    with pytest.raises(ValidationError, match="unique"):
        Profile.from_path(path)


def test_example_platform_profile_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    profile = Profile.from_path(root / "examples/profiles/platform.yaml")

    assert profile.metadata.name == "platform"
    assert profile.namespace == "platform"
    assert profile.distribution.components.present_keys() == {
        "ewb",
        "eas",
        "hcs",
        "eas-web-client",
    }
    assert profile.distribution.components.eas_web_client == VersionLocator(
        version="1.40.0"
    )
    assert profile.kind.config["kind"] == "Cluster"
    assert profile.terraform is not None
    assert profile.terraform.contracts == ["eas", "hcs"]
    assert profile.kind.host_mounts[0].slot == "ewb-data"
    assert profile.kind.host_mounts[0].node_path == "/mnt/ewb-data"
    assert profile.requires_bindings() is True
    helpers = profile.to_cluster_components()
    assert helpers.source_dir == profile.source_dir
    assert {c.name for c in helpers.cluster_components} == {
        "cnpg",
        "eas-kind-pg",
        "hcs-kind-pg",
        "eas-nodeport",
    }
    assert profile.source_dir is not None
    assert not (profile.source_dir / "stubs").exists()
    assert not (profile.source_dir / "post-apps").exists()
    assert profile.apps["ewb"].values["loadDatabase"]["enabled"] is False
    assert profile.apps["eas-web-client"].values["image"]["tag"] == "1.40.0"
    web_values = profile.apps["eas-web-client"].values
    assert web_values["nodePort"] == {"enabled": True, "port": 30080}
    assert web_values["config"]["auth"]["authType"] == "none"
    assert web_values["config"]["eas"] == {
        "host": "127.0.0.1",
        "port": 8081,
        "protocol": "http",
    }
    assert profile.secrets == []
    for component in profile.cluster_components:
        if isinstance(component, LocalManifestComponent):
            assert all(
                (profile.source_dir / manifest).is_file()
                for manifest in component.manifests
            )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda p, hcs: hcs["spec"].update(bootstrap={}), "spec.bootstrap"),
        (lambda p, hcs: hcs.update(namespace="other"), "profile.namespace"),
        (lambda p, hcs: hcs["databases"].update(hcs={}), "primary database"),
        (lambda p, hcs: hcs["spec"].update(imageName="other"), "image_catalog"),
        (
            lambda p, hcs: hcs["image_catalog"].update(major=9),
            "greater than or equal to 10",
        ),
    ],
    ids=[
        "bootstrap",
        "namespace",
        "duplicate-database",
        "image-selection",
        "unsupported-postgres-major",
    ],
)
def test_reference_profile_rejects_invalid_database_contract(
    change: Callable[[dict[str, Any], dict[str, Any]], object], message: str
) -> None:
    root = Path(__file__).resolve().parents[1] / "examples"
    raw = yaml.safe_load((root / "profiles/platform.yaml").read_text(encoding="utf-8"))
    hcs = next(
        component
        for component in raw["cluster_components"]
        if component["name"] == "hcs-kind-pg"
    )
    change(raw, hcs)
    distribution = Distribution.from_path(root / "distributions/platform.yaml")

    with pytest.raises(ValidationError, match=message):
        Profile.model_validate({**raw, "distribution": distribution})
