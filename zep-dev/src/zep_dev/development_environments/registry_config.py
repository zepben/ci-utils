"""Read container registry authentication configuration."""

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError


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
