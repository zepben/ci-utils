from collections.abc import Callable
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from tests.support.fixtures import WriteDistribution
from zep_dev.development_environments.documents import (
    load_template,
    load_yaml,
)


@pytest.mark.parametrize(
    "source",
    [
        "metadata: {name: one, name: two}\ncharts: {eas: {version: 1.0.0}}\n",
        "metadata: {name: one}\ncharts: {eas: {version: 1.0.0}, eas: {version: 2.0.0}}\n",
    ],
)
def test_duplicate_yaml_keys_are_rejected_before_validation(source: str) -> None:
    with pytest.raises(ValueError, match="duplicate YAML mapping key"):
        load_yaml(StringIO(source))


def test_distribution_is_template_relative_and_cross_namespace_cnpg_is_valid(
    write_distribution: WriteDistribution,
    basic_template: dict[str, Any],
    write_template: Callable[[dict[str, Any]], Path],
) -> None:
    basic_template.update(
        {
            "distribution": "dist.yaml",
            "services": {
                "eas-postgres": {
                    "type": "cnpg",
                    "namespace": "databases",
                    "database": "eas",
                    "owner": "eas",
                    "password": "test",
                    "spec": {"instances": 1},
                }
            },
            "applications": {
                "eas": {
                    "databases": {
                        "primary": {"service": "eas-postgres", "database": "eas"}
                    },
                    "values": {"deploymentProfile": "kindTest"},
                }
            },
            "inputs": {"repositories": ["deployments"]},
        }
    )
    path = write_template(basic_template)
    write_distribution(eas={"version": "1.0.0"})
    template, distribution = load_template(path)
    assert distribution is not None
    assert list(distribution.charts) == ["eas"]
    assert "primary" in template.applications["eas"].databases


@pytest.mark.parametrize("source", ["123: value\n", "true: value\n"])
def test_mapping_rejects_non_string_keys(tmp_path: Path, source: str) -> None:
    from zep_dev.development_environments.documents import read_mapping

    path = tmp_path / "document.yaml"
    path.write_text(source)
    with pytest.raises(ValueError, match="mapping with string keys"):
        read_mapping(path)


def test_mapping_preserves_yaml_values_outside_json(tmp_path: Path) -> None:
    from datetime import date

    from zep_dev.development_environments.documents import read_mapping

    path = tmp_path / "document.yaml"
    path.write_text("date: 2026-10-13\nsettings: {replicas: 2}\n")
    assert read_mapping(path) == {
        "date": date(2026, 10, 13),
        "settings": {"replicas": 2},
    }
