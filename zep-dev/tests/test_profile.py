from pathlib import Path

import pytest
from pydantic import ValidationError

from zep_dev.bindings import Bindings
from zep_dev.profile import Profile, load_profile_metadata


def test_profile_from_path_nests_distribution(write_profile) -> None:
    path = write_profile(
        ewb={"version": "1.0.0"},
        body={
            "apps": {"ewb": {"deploymentProfile": "kindTest"}},
            "runtime": {
                "manifests": [{"namespace": "integration", "files": ["m.yaml"]}]
            },
        },
    )
    profile = Profile.from_path(path)
    assert profile.distribution.charts["ewb"] is not None
    assert profile.apps["ewb"]["deploymentProfile"] == "kindTest"
    assert profile.runtime.manifests[0].files == ["m.yaml"]


def test_profile_rejects_apps_outside_distribution(
    write_profile,
) -> None:
    with pytest.raises(ValidationError, match="subset of distribution"):
        Profile.from_path(
            write_profile(
                ewb={"version": "1.0.0"},
                body={"apps": {"hcs": {"x": 1}}},
            )
        )


def test_profile_accepts_chart_named_helm_values(write_profile) -> None:
    values = {"chart": "value", "version": "value", "repository": "value"}
    profile = Profile.from_path(write_profile(body={"apps": {"ewb": values}}))
    assert profile.apps["ewb"] == values


def test_sorting_rule_keeps_host_paths_and_deployments_root_out_of_profile(
    write_profile,
) -> None:
    with pytest.raises(ValidationError):
        Profile.from_path(
            write_profile(
                body={
                    "k8s": {
                        "mounts": [
                            {
                                "slot": "ewb-data",
                                "node_path": "/mnt/x",
                                "host_path": "/tmp/x",
                            }
                        ]
                    }
                }
            )
        )
    with pytest.raises(ValidationError):
        Profile.from_path(write_profile(body={"runtime": {"deployments_root": "/tmp"}}))


def test_databases_must_name_cnpg(write_profile) -> None:
    with pytest.raises(ValidationError, match="CNPG"):
        Profile.from_path(
            write_profile(body={"runtime": {"databases": {"eas": "missing"}}})
        )


def test_load_profile_metadata_skips_distribution(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(
        "metadata:\n  name: only-meta\ndistribution: missing.yaml\n",
        encoding="utf-8",
    )
    assert load_profile_metadata(path).name == "only-meta"


def test_resolved_host_mounts(tmp_path: Path, write_profile) -> None:
    path = write_profile(
        body={"k8s": {"mounts": [{"slot": "ewb-data", "node_path": "/mnt/ewb-data"}]}}
    )
    data = tmp_path / "data"
    data.mkdir()
    mounts = Profile.from_path(path).resolved_host_mounts(
        Bindings(mounts={"ewb-data": data})
    )
    assert len(mounts) == 1
    assert mounts[0].node_path == "/mnt/ewb-data"
    assert mounts[0].host_path == data.resolve()


def test_example_integration_profile_loads() -> None:
    root = Path(__file__).resolve().parents[1]
    profile = Profile.from_path(root / "examples/integration/profile.yaml")
    assert profile.metadata.name == "integration"
    assert "eas" in profile.runtime.databases
