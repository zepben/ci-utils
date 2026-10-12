from typing import Any

import pytest
from pydantic import ValidationError

from zep_dev.development_environments.distributions import Distribution
from zep_dev.development_environments.templates import (
    EnvironmentTemplate,
    validate_distribution,
)


def test_application_without_distribution_is_rejected(
    basic_template: dict[str, Any],
) -> None:
    basic_template["applications"] = {"eas": {}}
    with pytest.raises(ValidationError, match="requires a Distribution"):
        EnvironmentTemplate.model_validate(basic_template)


def test_mount_requires_declared_input_and_worker(
    basic_template: dict[str, Any],
) -> None:
    basic_template["cluster"]["mounts"] = [{"slot": "data", "node_path": "/mnt/data"}]
    with pytest.raises(ValidationError, match="not declared"):
        EnvironmentTemplate.model_validate(basic_template)
    basic_template["inputs"] = {"mounts": ["data"]}
    basic_template["cluster"]["kind"]["nodes"] = [{"role": "control-plane"}]
    with pytest.raises(ValidationError, match="worker"):
        EnvironmentTemplate.model_validate(basic_template)


def test_argo_repository_must_be_declared(basic_template: dict[str, Any]) -> None:
    basic_template["services"] = {
        "argo": {
            "type": "helm",
            "chart": "argo-cd",
            "repository": "https://argoproj.github.io/argo-helm",
            "version": "1.0",
            "integration": {"type": "argo-cd", "repositories": ["deployments"]},
        }
    }
    with pytest.raises(ValidationError, match="undeclared"):
        EnvironmentTemplate.model_validate(basic_template)
    basic_template["inputs"] = {"repositories": ["deployments"]}
    assert (
        EnvironmentTemplate.model_validate(basic_template).services["argo"] is not None
    )


def test_cnpg_reference_must_name_cnpg_and_deployments(
    basic_template: dict[str, Any],
) -> None:
    basic_template["distribution"] = "dist.yaml"
    basic_template["applications"] = {"eas": {"database": {"service": "missing"}}}
    with pytest.raises(ValidationError, match="CNPG"):
        EnvironmentTemplate.model_validate(basic_template)
    basic_template["services"] = {
        "missing": {
            "type": "cnpg",
            "database": "eas",
            "owner": "eas",
            "password": "test",
            "spec": {},
        }
    }
    with pytest.raises(ValidationError, match="deployments"):
        EnvironmentTemplate.model_validate(basic_template)


def test_service_and_application_names_may_not_collide(
    basic_template: dict[str, Any],
) -> None:
    basic_template["distribution"] = "dist.yaml"
    basic_template["services"] = {
        "eas": {"type": "raw", "manifests": ["https://example.org/a.yaml"]}
    }
    template = EnvironmentTemplate.model_validate(basic_template)
    distribution = Distribution.model_validate(
        {"metadata": {"name": "test"}, "charts": {"eas": {"version": "1.0.0"}}}
    )
    with pytest.raises(ValueError, match="collide"):
        validate_distribution(template, distribution)


def test_application_must_be_selected(
    basic_template: dict[str, Any],
) -> None:
    basic_template.update(distribution="dist.yaml", applications={"eas": {}})
    template = EnvironmentTemplate.model_validate(basic_template)
    distribution = Distribution.model_validate(
        {"metadata": {"name": "test"}, "charts": {"ewb": {"version": "1.0.0"}}}
    )
    with pytest.raises(ValueError, match="not selected"):
        validate_distribution(template, distribution)


def test_helm_release_length_limit(basic_template: dict[str, Any]) -> None:
    service = {
        "type": "helm",
        "chart": "helper",
        "repository": "https://example.org/charts",
        "version": "1",
    }
    basic_template["services"] = {"a" * 53: service}
    assert len(EnvironmentTemplate.model_validate(basic_template).services) == 1
    basic_template["services"] = {"a" * 54: service}
    with pytest.raises(ValidationError, match="Helm release names"):
        EnvironmentTemplate.model_validate(basic_template)


@pytest.mark.parametrize(
    ("mounts", "slots", "message"),
    [
        (
            [
                {"slot": "one", "node_path": "/one"},
                {"slot": "one", "node_path": "/two"},
            ],
            ["one"],
            "slot names must be unique",
        ),
        (
            [
                {"slot": "one", "node_path": "/same"},
                {"slot": "two", "node_path": "/same"},
            ],
            ["one", "two"],
            "node paths must be unique",
        ),
    ],
    ids=["duplicate-slot", "duplicate-destination"],
)
def test_mounts_have_unique_sources_and_destinations(
    basic_template: dict[str, Any],
    mounts: list[dict[str, str]],
    slots: list[str],
    message: str,
) -> None:
    basic_template["cluster"]["mounts"] = mounts
    basic_template["inputs"] = {"mounts": slots}
    with pytest.raises(ValidationError, match=message):
        EnvironmentTemplate.model_validate(basic_template)


@pytest.mark.parametrize(
    "inputs",
    [
        {"mounts": ["data", "data"]},
        {"repositories": ["deployments", "deployments"]},
        {"secrets": {"one": {"name": "same"}, "two": {"name": "same"}}},
    ],
    ids=["mounts", "repositories", "secret-names"],
)
def test_declared_inputs_have_unique_identity(
    basic_template: dict[str, Any], inputs: dict[str, Any]
) -> None:
    basic_template["inputs"] = inputs
    with pytest.raises(ValidationError, match="duplicate"):
        EnvironmentTemplate.model_validate(basic_template)


def test_declared_mount_requires_a_consumer(basic_template: dict[str, Any]) -> None:
    basic_template["inputs"] = {"mounts": ["unused"]}
    with pytest.raises(ValidationError, match="no consumer"):
        EnvironmentTemplate.model_validate(basic_template)


@pytest.mark.parametrize("application", ["ewb", "eas-web-client"])
def test_database_reference_is_limited_to_supported_applications(
    basic_template: dict[str, Any], application: str
) -> None:
    basic_template.update(
        distribution="distribution.yaml",
        inputs={"repositories": ["deployments"]},
        services={
            "database": {
                "type": "cnpg",
                "database": "app",
                "owner": "app",
                "password": "test",
                "spec": {},
            }
        },
        applications={application: {"database": {"service": "database"}}},
    )
    with pytest.raises(ValidationError, match="database is unsupported"):
        EnvironmentTemplate.model_validate(basic_template)


@pytest.mark.parametrize(
    "nodes",
    [
        [{"role": "workre"}],
        [{"role": "worker", "extraMounts": {}}],
        [
            {
                "role": "worker",
                "extraMounts": [{"hostPath": 123, "containerPath": "/data"}],
            }
        ],
        [
            {
                "role": "worker",
                "extraMounts": [
                    {"hostPath": "/data", "containerPath": "/data", "readOnly": "false"}
                ],
            }
        ],
    ],
    ids=[
        "invalid-role",
        "mounts-not-a-list",
        "invalid-host-path",
        "invalid-mount-mode",
    ],
)
def test_kind_consumed_fields_are_validated(
    basic_template: dict[str, Any], nodes: object
) -> None:
    basic_template["cluster"]["kind"]["nodes"] = nodes
    with pytest.raises(ValueError):
        EnvironmentTemplate.model_validate(basic_template)
