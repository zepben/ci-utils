import pytest

from tests.support.charts import pulls_published_chart
from tests.support.execution import FakeExecuteFactory
from zep_dev.charts import published
from zep_dev.errors import ZepDevError


@pytest.mark.parametrize(
    "detail",
    ["401 Unauthorized", "connection refused"],
    ids=["authentication", "network"],
)
def test_published_chart_lookup_propagates_errors_other_than_missing_chart(
    fake_execute: FakeExecuteFactory, detail: str
) -> None:
    fake_execute(published).on("helm", "pull", returncode=1, stderr=detail)
    with pytest.raises(ZepDevError, match=detail):
        published.published_chart_metadata("eas", "1.2.3")


@pytest.mark.parametrize("detail", ["manifest unknown", "404 Not Found"])
def test_published_chart_lookup_identifies_missing_chart(
    fake_execute: FakeExecuteFactory, detail: str
) -> None:
    fake_execute(published).on("helm", "pull", returncode=1, stderr=detail)
    assert published.published_chart_metadata("eas", "1.2.3") is None


def test_published_chart_metadata_is_read_from_the_pulled_chart(
    fake_execute: FakeExecuteFactory,
) -> None:
    annotations = {"zepben.com/runtime-contract-ref": "abc"}
    fake_execute(published).on("helm", "pull", hook=pulls_published_chart(annotations))

    metadata = published.published_chart_metadata("eas", "0.0.0-2.20.0.7+4930f10")

    assert metadata is not None
    assert metadata.name == "eas"
    assert metadata.version == "0.0.0-2.20.0.7+4930f10"
    assert metadata.annotations == annotations
