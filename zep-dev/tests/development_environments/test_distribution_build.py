"""Distribution builds check published charts and preserve selection documents."""

import pytest
from click.testing import CliRunner

from tests.support.charts import pull_chart_package
from tests.support.execution import FakeExecuteFactory
from tests.support.fixtures import WriteDistribution
from zep_dev.charts import published
from zep_dev.cli import cli

pytestmark = pytest.mark.usefixtures("cli_environment")


def test_build_checks_selected_versions_and_preserves_document(
    write_distribution: WriteDistribution, fake_execute: FakeExecuteFactory
) -> None:
    path = write_distribution(
        hcs={"version": "2.0.0"},
        ewb={"version": "1.0.0"},
        eas={"version": "1.1.0"},
    )
    original = path.read_text(encoding="utf-8")
    fake = fake_execute(published).on("helm", "pull", hook=pull_chart_package)

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code == 0, result.exception or result.output
    assert sorted(
        (entry.args[2], entry.args[entry.args.index("--version") + 1])
        for entry in fake.calls_for("helm", "pull")
    ) == [
        ("oci://ghcr.io/zepben/charts/eas", "1.1.0"),
        ("oci://ghcr.io/zepben/charts/ewb", "1.0.0"),
        ("oci://ghcr.io/zepben/charts/hcs", "2.0.0"),
    ]
    assert path.read_text(encoding="utf-8") == original


def test_missing_version_stops_distribution_build(
    write_distribution: WriteDistribution, fake_execute: FakeExecuteFactory
) -> None:
    path = write_distribution(ewb={"version": "9.9.9"}, eas={"version": "1.0.0"})
    fake = fake_execute(published).on(
        "helm", "pull", returncode=1, stderr="manifest unknown"
    )

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert "Distribution charts ready" not in result.output
    assert result.exit_code != 0
    assert result.exception is not None
    assert "OCI not-found" in str(result.exception)
    assert "cannot build a version: locator" in str(result.exception)
    assert len(fake.calls) == 1
