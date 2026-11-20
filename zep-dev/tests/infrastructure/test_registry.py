from pathlib import Path

import pytest

from zep_dev.infrastructure import registry


@pytest.mark.parametrize("present", [(0, 1, 2), (1, 2), (2,), ()])
def test_registry_discovery_preserves_helm_containers_docker_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, present: tuple[int, ...]
) -> None:
    candidates = tuple(tmp_path / str(index) for index in range(3))
    monkeypatch.setattr(registry, "REGISTRY_CONFIG_PATHS", candidates)
    for index in present:
        candidates[index].write_text("{}")

    expected = candidates[present[0]] if present else None
    assert registry.resolve_registry_config() == expected


def test_registry_candidates_retain_the_existing_locations() -> None:
    home = Path.home()
    assert registry.REGISTRY_CONFIG_PATHS == (
        home / ".config/helm/registry/config.json",
        home / ".config/containers/auth.json",
        home / ".docker/config.json",
    )
