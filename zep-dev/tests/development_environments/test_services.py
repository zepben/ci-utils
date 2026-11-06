from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from zep_dev.development_environments.services import HelmService, SupportingService


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        pytest.param(
            {
                "type": "helm",
                "chart": "./local",
                "version": "1",
                "repository": "https://example.org",
            },
            "Helm chart requires",
            id="local-chart",
        ),
        pytest.param(
            {
                "type": "helm",
                "chart": "oci://example.org/charts/help",
                "version": "1",
                "repository": "https://example.org",
            },
            "OCI chart requires",
            id="oci-with-repository",
        ),
        pytest.param(
            {"type": "helm", "chart": "help", "version": "1"},
            "Helm chart requires",
            id="missing-repository",
        ),
        pytest.param(
            {"type": "raw", "manifests": ["http://example.org/a.yaml"]},
            "HTTPS URLs",
            id="insecure-manifest",
        ),
        pytest.param(
            {
                "type": "cnpg",
                "database": "eas",
                "owner": "eas",
                "password": "test",
                "spec": {"bootstrap": {}},
            },
            "spec.bootstrap is generated",
            id="generated-bootstrap",
        ),
        pytest.param(
            {
                "type": "cnpg",
                "database": "eas",
                "owner": "eas",
                "password": "test",
                "databases": {"eas": {}},
                "spec": {},
            },
            "primary database must not",
            id="duplicate-primary-database",
        ),
        pytest.param(
            {
                "type": "cnpg",
                "database": "eas",
                "owner": "eas",
                "password": "test",
                "image_catalog": {"major": 16, "image": "x"},
                "spec": {"imageName": "x"},
            },
            "image_catalog cannot",
            id="conflicting-image-selection",
        ),
    ],
)
def test_rejected_service_contracts(payload: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        TypeAdapter(SupportingService).validate_python(payload)


def test_oci_chart_is_valid_without_repository() -> None:
    service: SupportingService = TypeAdapter(SupportingService).validate_python(
        {"type": "helm", "chart": "oci://example.org/charts/helper", "version": "1"}
    )
    assert isinstance(service, HelmService)
    assert service.chart == "oci://example.org/charts/helper"
