"""Validate untrusted serialized values before exposing typed data."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

_MAPPING: TypeAdapter[dict[str, object]] = TypeAdapter(dict[str, object])


def string_mapping(value: object, context: str) -> dict[str, object]:
    """Require a mapping with string keys, preserving arbitrary YAML values."""
    try:
        return _MAPPING.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ValueError(f"{context}: expected a mapping with string keys") from exc


class RegistryCredential(BaseModel):
    model_config = ConfigDict(strict=True, hide_input_in_errors=True)

    auth: str | None = None


class RegistryConfig(BaseModel):
    model_config = ConfigDict(strict=True, hide_input_in_errors=True)

    auths: dict[str, RegistryCredential] = Field(default_factory=dict)
    credHelpers: dict[str, str] = Field(default_factory=dict)
    credsStore: str | None = None

    @classmethod
    def read(cls, path: Path) -> RegistryConfig:
        try:
            return cls.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError:
            raise ValueError(
                f"{path}: invalid container registry configuration"
            ) from None
