from dataclasses import dataclass, field
from typing import override

from zep_dev.development_environments.chart_sources import ChartRef, ChartResolver
from zep_dev.development_environments.distributions import (
    ChartLocator,
    ChartName,
    Charts,
)
from zep_dev.models import ChartMetadata


@dataclass
class RecordingChartResolver(ChartResolver):
    refs: list[ChartRef] = field(default_factory=list)
    resolutions: list[Charts] = field(default_factory=list)
    checked: list[ChartRef] = field(default_factory=list)
    resolved: list[tuple[ChartName, ChartLocator]] = field(default_factory=list)
    ensured: list[ChartRef] = field(default_factory=list)
    ensure_error: Exception | None = None

    def __post_init__(self) -> None:
        super().__init__()

    @override
    def resolve_all(self, charts: Charts) -> list[ChartRef]:
        self.resolutions.append(charts)
        return self.refs

    @override
    def check_all(self, refs: list[ChartRef]) -> list[ChartMetadata | None]:
        self.checked.extend(refs)
        return [None for _ref in refs]

    @override
    def resolve(self, name: ChartName, locator: ChartLocator) -> ChartRef:
        self.resolved.append((name, locator))
        return next(ref for ref in self.refs if ref.name == name)

    @override
    def ensure(self, ref: ChartRef) -> None:
        self.ensured.append(ref)
        if self.ensure_error is not None:
            raise self.ensure_error
