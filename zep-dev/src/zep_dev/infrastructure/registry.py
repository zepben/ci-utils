"""Discover the caller's Helm or container registry configuration."""

from pathlib import Path

REGISTRY_CONFIG_PATHS = (
    Path.home() / ".config" / "helm" / "registry" / "config.json",
    Path.home() / ".config" / "containers" / "auth.json",
    Path.home() / ".docker" / "config.json",
)


def resolve_registry_config() -> Path | None:
    return next((path for path in REGISTRY_CONFIG_PATHS if path.is_file()), None)
