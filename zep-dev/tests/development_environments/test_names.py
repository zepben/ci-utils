import pytest
from pydantic import TypeAdapter, ValidationError

from zep_dev.development_environments.names import EnvironmentName


def test_environment_name_leaves_room_for_cluster_prefix() -> None:
    adapter = TypeAdapter(EnvironmentName)
    assert adapter.validate_python("a" * 55) == "a" * 55
    with pytest.raises(ValidationError, match="derived Kind cluster name exceed 63"):
        adapter.validate_python("a" * 56)
