import pytest
from pydantic import ValidationError

from zep_dev.development_environments.bindings import Bindings


@pytest.mark.parametrize(
    "source",
    [{}, {"env": "ONE", "file": "/tmp/other"}],
    ids=["missing-source", "two-sources"],
)
def test_secret_binding_requires_one_source(source: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Bindings.model_validate({"secrets": {"credentials": source}})
