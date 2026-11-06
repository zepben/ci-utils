"""Runtime contract references: derived from a chart's Git history, pinned in Terraform roots."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from zep_dev.chart_version import git_prefix, git_toplevel
from zep_dev.charts.published import CHART_REPOSITORY, published_chart_metadata
from zep_dev.shared import execute

RUNTIME_CONTRACT_DIRECTORY = "runtime-contract"
RUNTIME_CONTRACT_REF_ANNOTATION = "zepben.com/runtime-contract-ref"
_TERRAFORM_ROOT_ANNOTATION = "zepben.com/terraform-root"
_SOURCE_ANNOTATION = "org.opencontainers.image.source"
_APPLICATION_FILE = "application.yaml"
_PINS_FILE = "runtime-contracts.tf.json"


def runtime_contract_ref(chart: Path) -> str | None:
    if not (chart / RUNTIME_CONTRACT_DIRECTORY).is_dir():
        return None
    ref = execute(
        *git_prefix(chart),
        "log",
        "-1",
        "--format=%H",
        "--",
        RUNTIME_CONTRACT_DIRECTORY,
        skip_resolve=True,
        capture_stdout=True,
    ).stdout.strip()
    if not ref:
        raise ValueError(
            f"no commit touches {chart / RUNTIME_CONTRACT_DIRECTORY}; "
            "commit the runtime contract before releasing the chart"
        )
    return ref


class _Source(BaseModel):
    repoURL: str
    chart: str | None = None
    targetRevision: str | None = None


class _Metadata(BaseModel):
    name: str
    annotations: dict[str, str] = Field(default_factory=dict)


class _Spec(BaseModel):
    sources: list[_Source]


class _ApplicationDocument(BaseModel):
    kind: Literal["Application"]
    metadata: _Metadata
    spec: _Spec


@dataclass(frozen=True)
class DeployedChart:
    name: str
    version: str


@dataclass(frozen=True)
class ArgoApplication:
    """An Argo CD Application, with the zepben charts it deploys."""

    path: Path
    name: str
    terraform_root: Path | None
    """Relative to the repository, from the zepben.com/terraform-root annotation."""
    charts: tuple[DeployedChart, ...]


def read_applications(paths: list[Path]) -> list[ArgoApplication]:
    """Read Application files; a directory gives the Applications under it that name a Terraform root."""
    applications: list[ArgoApplication] = []
    for path in paths:
        if path.is_dir():
            for file in sorted(path.rglob(_APPLICATION_FILE)):
                content = _load(file)
                if _names_terraform_root(content):
                    applications.append(_application(file, content))
        else:
            applications.append(_application(path, _load(path)))
    return applications


def _load(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _names_terraform_root(content: object) -> bool:
    metadata = content.get("metadata") if isinstance(content, dict) else None
    annotations = metadata.get("annotations") if isinstance(metadata, dict) else None
    return isinstance(annotations, dict) and _TERRAFORM_ROOT_ANNOTATION in annotations


def _application(path: Path, content: object) -> ArgoApplication:
    try:
        document = _ApplicationDocument.model_validate(content)
    except ValidationError as error:
        raise ValueError(f"{path} is not an Argo CD Application: {error}") from error
    charts = []
    for source in document.spec.sources:
        if source.repoURL != CHART_REPOSITORY:
            continue
        if source.chart is None or source.targetRevision is None:
            raise ValueError(
                f"{path}: {CHART_REPOSITORY} source needs chart and targetRevision"
            )
        charts.append(DeployedChart(source.chart, source.targetRevision))
    root = document.metadata.annotations.get(_TERRAFORM_ROOT_ANNOTATION)
    return ArgoApplication(
        path=path,
        name=document.metadata.name,
        terraform_root=Path(root) if root is not None else None,
        charts=tuple(charts),
    )


def _pin_name(chart: str) -> str:
    return f"{chart.replace('-', '_')}_runtime_contract_ref"


def _read_pins(root: Path) -> dict[str, str]:
    if not root.is_dir():
        raise ValueError(f"Terraform root {root} does not exist")
    path = root / _PINS_FILE
    if not path.exists():
        return {}
    content = json.loads(path.read_text(encoding="utf-8"))
    pins = content.get("locals") if isinstance(content, dict) else None
    if not isinstance(pins, dict):
        raise ValueError(f"{path} must contain a locals object")
    return pins


def _write_pins(root: Path, pins: dict[str, str]) -> None:
    content = json.dumps({"locals": dict(sorted(pins.items()))}, indent=2)
    (root / _PINS_FILE).write_text(f"{content}\n", encoding="utf-8")


type PinStatus = Literal["already_pinned", "outdated", "pinned"]


@dataclass(frozen=True)
class PinOutcome:
    status: PinStatus
    ref: str
    previous: str | None
    root: Path
    source: str | None
    """The chart's source repository URL, for linking contract changes."""


def pin_runtime_contract(
    application: ArgoApplication, chart: DeployedChart, *, check: bool
) -> PinOutcome | None:
    """Pin the Application's Terraform root to the runtime contract its chart needs.

    Return None when the chart has no runtime contract. With check, report an
    outdated pin without writing it.
    """
    label = f"{application.name}: {chart.name} {chart.version}"
    metadata = published_chart_metadata(chart.name, chart.version)
    if metadata is None:
        raise ValueError(f"{label}: chart is not published")
    ref = metadata.annotations.get(RUNTIME_CONTRACT_REF_ANNOTATION)
    if ref is None:
        return None
    root = application.terraform_root
    if root is None:
        raise ValueError(
            f"{label}: chart needs runtime contract {ref}, "
            f"but {application.path} has no {_TERRAFORM_ROOT_ANNOTATION} annotation"
        )
    directory = git_toplevel(application.path.parent) / root
    name = _pin_name(chart.name)
    pins = _read_pins(directory)
    previous = pins.get(name)
    source = metadata.annotations.get(_SOURCE_ANNOTATION)
    if previous == ref:
        status: PinStatus = "already_pinned"
    elif check:
        status = "outdated"
    else:
        _write_pins(directory, {**pins, name: ref})
        status = "pinned"
    return PinOutcome(status, ref, previous, root, source)
