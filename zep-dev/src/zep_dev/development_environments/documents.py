"""Duplicate-safe YAML loading and document-relative references."""

from pathlib import Path
from typing import TextIO

import yaml
from pydantic import TypeAdapter, ValidationError

from zep_dev.development_environments.distributions import Distribution
from zep_dev.development_environments.templates import (
    EnvironmentTemplate,
    validate_distribution,
)
from zep_dev.errors import ZepDevError

_MAPPING: TypeAdapter[dict[str, object]] = TypeAdapter(dict[str, object])


def string_mapping(value: object, context: str) -> dict[str, object]:
    """Require a mapping with string keys, preserving arbitrary YAML values."""
    try:
        return _MAPPING.validate_python(value, strict=True)
    except ValidationError as exc:
        raise ValueError(f"{context}: expected a mapping with string keys") from exc


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def mapping_without_duplicates(
    loader: UniqueKeyLoader, node: yaml.MappingNode
) -> dict[object, object]:
    result: dict[object, object] = {}
    for key_node, value_node in node.value:
        key: object = loader.construct_object(key_node, deep=True)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                None, None, "unhashable YAML mapping key", key_node.start_mark
            ) from exc
        if duplicate:
            raise yaml.constructor.ConstructorError(
                None, None, f"duplicate YAML mapping key: {key!r}", key_node.start_mark
            )
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping_without_duplicates
)


def load_yaml(source: TextIO) -> object:
    try:
        return yaml.load(source, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"{getattr(source, 'name', '<input>')}: {exc}") from exc


def read_mapping(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as source:
        data = load_yaml(source)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: YAML document must be a mapping")
    return string_mapping(data, str(path))


def load_distribution(path: Path) -> Distribution:
    return Distribution.model_validate(read_mapping(path))


def load_template(path: Path) -> tuple[EnvironmentTemplate, Distribution | None]:
    template = EnvironmentTemplate.model_validate(read_mapping(path))
    distribution = None
    if template.distribution is not None:
        distribution_path = resolve_relative(path, template.distribution)
        if not distribution_path.is_file():
            raise ZepDevError(f"{path}: Distribution not found: {distribution_path}")
        distribution = load_distribution(distribution_path)
    validate_distribution(template, distribution)
    return template, distribution


def resolve_relative(source: Path, reference: str) -> Path:
    return (source.parent / reference).resolve()
