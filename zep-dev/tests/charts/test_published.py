import pytest

from tests.support.execution import FakeExecuteFactory
from zep_dev.charts import published


@pytest.mark.parametrize(
    "detail",
    ["401 Unauthorized", "connection refused"],
    ids=["authentication", "network"],
)
def test_published_chart_lookup_propagates_errors_other_than_missing_chart(
    fake_execute: FakeExecuteFactory, detail: str
) -> None:
    fake_execute(published).on("helm", "pull", returncode=1, stderr=detail)
    with pytest.raises(RuntimeError, match=detail):
        published.published_chart_metadata("eas", "1.2.3")


@pytest.mark.parametrize("detail", ["manifest unknown", "404 Not Found"])
def test_published_chart_lookup_identifies_missing_chart(
    fake_execute: FakeExecuteFactory, detail: str
) -> None:
    fake_execute(published).on("helm", "pull", returncode=1, stderr=detail)
    assert published.published_chart_metadata("eas", "1.2.3") is None
