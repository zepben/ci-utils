"""Shared chart metadata, publication annotations and application image values."""

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ChartDependency(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    repository: str = Field(min_length=1)


# When this annotation is "true", the chart is published with the application image
# built from the same revision, and its values.yaml image.tag names that image.
PUBLISH_ANNOTATION = "zepben.com/publish-with-application-image"


class ChartMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    type: str = "application"
    appVersion: str | None = None
    annotations: dict[str, str] = Field(default_factory=dict)
    dependencies: list[ChartDependency] = Field(default_factory=list)

    @property
    def publishes_application_image(self) -> bool:
        return self.annotations.get(PUBLISH_ANNOTATION) == "true"

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        chart_yaml = chart_dir / "Chart.yaml"
        if not chart_yaml.is_file():
            raise ValueError(f"Chart.yaml not found at {chart_yaml}")
        return cls.model_validate(yaml.safe_load(chart_yaml.read_text()))

    def write(self, chart_dir: Path) -> None:
        (chart_dir / "Chart.yaml").write_text(
            yaml.safe_dump(
                self.model_dump(mode="json", exclude_unset=True),
                sort_keys=False,
            )
        )


class ChartImageValues(BaseModel):
    model_config = ConfigDict(extra="allow")

    tag: str | None = None


class ChartValues(BaseModel):
    model_config = ConfigDict(extra="allow")

    image: ChartImageValues = Field(default_factory=ChartImageValues)

    @classmethod
    def from_chart_dir(cls, chart_dir: Path) -> Self:
        values_yaml = chart_dir / "values.yaml"
        if not values_yaml.is_file():
            return cls()
        return cls.model_validate(yaml.safe_load(values_yaml.read_text()))

    def write(self, chart_dir: Path) -> None:
        (chart_dir / "values.yaml").write_text(
            yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False)
        )
