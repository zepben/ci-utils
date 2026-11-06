import pytest
from pydantic import ValidationError

from zep_dev.development_environments.bindings import Bindings


@pytest.mark.parametrize(
    "source",
    [{}, {"env": "ONE", "file": "/tmp/other"}],
    ids=["missing-source", "two-sources"],
)
def test_secret_binding_requires_one_source(source: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="exactly one of env or file"):
        Bindings.model_validate({"secrets": {"credentials": source}})


def test_bindings_never_hold_a_secret_value() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Bindings.model_validate({"secrets": {"credentials": {"value": "hunter2"}}})
