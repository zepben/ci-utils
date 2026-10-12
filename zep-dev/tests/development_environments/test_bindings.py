import pytest
from pydantic import ValidationError

from zep_dev.development_environments.bindings import Bindings


@pytest.mark.parametrize(
    "source",
    [{}, {"env": "ONE", "file": "/tmp/other"}, {"file": "relative"}],
    ids=["missing-source", "two-sources", "relative-file"],
)
def test_secret_binding_requires_one_absolute_source(source: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        Bindings.model_validate({"secrets": {"credentials": source}})


@pytest.mark.parametrize("group", ["mounts", "repositories"])
def test_bound_directories_must_be_absolute(group: str) -> None:
    with pytest.raises(ValidationError, match="absolute"):
        Bindings.model_validate({group: {"key": "relative"}})
