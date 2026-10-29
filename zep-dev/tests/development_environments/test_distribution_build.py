"""Distribution builds check published charts and preserve selection documents."""

import pytest
from click.testing import CliRunner

from tests.support.charts import published_chart
from tests.support.execution import FakeExecuteFactory, option_value
from tests.support.fixtures import WriteDistribution
from zep_dev.charts import published
from zep_dev.cli import cli

pytestmark = pytest.mark.usefixtures("cli_environment")


def test_build_checks_selected_versions_and_preserves_document(
    write_distribution: WriteDistribution, fake_execute: FakeExecuteFactory
) -> None:
    selected = {"hcs": "2.0.0", "ewb": "1.0.0", "eas": "1.1.0"}
    path = write_distribution(
        hcs={"version": selected["hcs"]},
        ewb={"version": selected["ewb"]},
        eas={"version": selected["eas"]},
    )
    original = path.read_text(encoding="utf-8")
    fake = fake_execute(published)
    for name, version in selected.items():
        fake.on(
            "helm",
            "show",
            "chart",
            f"oci://ghcr.io/zepben/charts/{name}",
            "--version",
            version,
            stdout=published_chart(name, version),
        )

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code == 0, result.exception or result.output
    assert sorted(
        (entry.args[3], option_value(entry.args, "--version"))
        for entry in fake.calls_for("helm", "show", "chart")
    ) == sorted(
        (f"oci://ghcr.io/zepben/charts/{name}", version)
        for name, version in selected.items()
    )
    assert path.read_text(encoding="utf-8") == original


def test_missing_version_stops_distribution_build(
    write_distribution: WriteDistribution, fake_execute: FakeExecuteFactory
) -> None:
    path = write_distribution(ewb={"version": "9.9.9"}, eas={"version": "1.0.0"})
    fake = fake_execute(published).on(
        "helm", "show", "chart", returncode=1, stderr="manifest unknown"
    )

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert "Distribution charts ready" not in result.output
    assert result.exit_code == 1
    assert "OCI not-found" in result.stderr
    assert "cannot build a version: locator" in result.stderr
    assert len(fake.calls) == 1
