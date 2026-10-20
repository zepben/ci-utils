import logging
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from subprocess import CalledProcessError
from tempfile import TemporaryDirectory
from typing import Any

import yaml
from click import ClickException

from zep_dev.cluster import (
    CLUSTER_NAME,
    add_helm_repos,
    helm,
    kind,
    load_image_archive,
    resolve_chart_path,
)
from zep_dev.commands.chart.utils import discover_charts
from zep_dev.models import (
    ApplicationHelm,
    ChartMetadata,
    ClusterComponent,
    ClusterComponents,
    ImageApplication,
)
from zep_dev.shared import execute
from zep_dev.static import CT_YAML

LOG = logging.getLogger(__name__)

DEFAULT_EXCLUDES = (
    "registry.k8s.io/*",
    "docker.io/kindest/*",
    "*/pause*",
    "*pause:*",
    "*kindnet*",
    "*coredns*",
    "*local-path*",
    "import-*",
)


@dataclass(frozen=True)
class HelmRender:
    chart: str
    release: str
    version: str | None = None
    namespace: str | None = None
    values: tuple[Path | Mapping[str, Any], ...] = ()


def render_image_refs(spec: HelmRender) -> set[str]:
    with TemporaryDirectory() as tmpdir:
        args = ["template", spec.release, spec.chart]
        if spec.namespace is not None:
            args.extend(["--namespace", spec.namespace])
        if spec.version is not None:
            args.extend(["--version", spec.version])
        for index, layer in enumerate(spec.values):
            if isinstance(layer, Path):
                values_path = layer
            else:
                values_path = Path(tmpdir) / f"values-{index}.yaml"
                values_path.write_text(yaml.safe_dump(dict(layer)), encoding="utf-8")
            args.extend(["-f", str(values_path)])
        return extract_image_refs(helm(*args, capture_stdout=True).stdout)


def choose_engine() -> str:
    for engine in ("podman", "docker"):
        try:
            execute(
                engine,
                "version",
                capture_stdout=True,
                capture_stderr=True,
                skip_resolve=True,
            )
        except CalledProcessError, OSError:
            continue
        return engine
    raise ClickException("neither podman nor docker is available")


def parse_image_refs(output: str) -> set[str]:
    refs: set[str] = set()
    for line in output.splitlines():
        columns = line.split()
        if not columns:
            continue

        ref = columns[0]
        # ctr emits bare content-address aliases alongside named references.
        # They cannot identify the workload image after the archive is loaded.
        if ref == "REF" or ref.startswith("sha256:"):
            continue

        if "@sha256:" in ref:
            name, digest = ref.split("@sha256:", maxsplit=1)
            if name and digest:
                refs.add(ref)
            continue

        # Split from the right so a registry port is not mistaken for a tag.
        name, separator, tag = ref.rpartition(":")
        if separator and name and tag and "/" not in tag:
            refs.add(ref)

    return refs


def is_tagged_image_ref(ref: str) -> bool:
    return re.fullmatch(r"[^@]+:[^/@:]+", ref) is not None


def select_image_refs(refs: Iterable[str], includes: Sequence[str]) -> list[str]:
    # Digest references fail when loaded into a fresh cluster, so only include
    # images with tags.
    selected = {ref for ref in refs if is_tagged_image_ref(ref)}
    if includes:
        selected = {
            ref for ref in selected if any(fnmatch(ref, glob) for glob in includes)
        }
    selected = {
        ref
        for ref in selected
        if not any(fnmatch(ref, glob) for glob in DEFAULT_EXCLUDES)
    }
    return sorted(selected)


def discover_image_refs(engine: str, includes: Sequence[str]) -> list[str]:
    nodes = kind(
        "get", "nodes", "--name", CLUSTER_NAME, capture_stdout=True
    ).stdout.splitlines()

    refs: set[str] = set()
    for node in nodes:
        image_output = execute(
            engine,
            "exec",
            node,
            "ctr",
            "--namespace=k8s.io",
            "images",
            "ls",
            capture_stdout=True,
            skip_resolve=True,
        ).stdout
        refs.update(parse_image_refs(image_output))

    selected = select_image_refs(refs, includes)
    if not selected:
        raise ClickException("no images selected")
    return selected


def dump_images(output: Path, includes: Sequence[str]) -> None:
    engine = choose_engine()
    selected = discover_image_refs(engine, includes)

    LOG.info("Using container engine: %s", engine)
    pull_missing_images(engine, selected)
    save_image_archive(engine, output, selected)


def prepare_chart_dependencies(chart_dir: Path) -> None:
    metadata = ChartMetadata.from_chart_dir(chart_dir)
    if metadata.dependencies:
        helm("dependency", "build", str(chart_dir), capture_stdout=True)


def parse_repository_mappings(mappings: Sequence[str]) -> dict[str, Path]:
    repositories: dict[str, Path] = {}
    for mapping in mappings:
        url, directory = mapping.split("=", 1)
        if not url or not directory:
            raise ValueError("--repository requires nonempty URL and PATH")
        root = Path(directory).resolve()
        if url in repositories and repositories[url] != root:
            raise ValueError(f"conflicting repository mappings for {url}")
        repositories[url] = root
    return repositories


def discover_application_image_refs(
    application: Path, repositories: Mapping[str, Path]
) -> set[str]:
    document = ImageApplication.model_validate(
        yaml.safe_load(application.read_text(encoding="utf-8"))
    )
    (chart,) = (source for source in document.sources if source.chart is not None)
    revision = chart.targetRevision
    # Skip floating revisions; Helm validates exact version syntax.
    if not re.fullmatch(
        r"v?[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?", revision
    ):
        LOG.warning(
            "%s: skipping Application with non-version chart revision %r",
            application,
            revision,
        )
        return set()
    for source in document.sources:
        if source.model_extra:
            raise ValueError(
                f"unsupported source fields: {', '.join(source.model_extra)}"
            )
    repository = chart.repoURL
    if "://" in repository and not repository.startswith("oci://"):
        raise ValueError("only OCI chart repositories are supported")
    chart_name = chart.chart
    assert chart_name is not None
    if chart.ref is not None:
        raise ValueError("chart sources with ref are unsupported")
    options = ApplicationHelm.model_validate(chart.helm)
    values_sources = {}
    for source in document.sources:
        if source is chart:
            continue
        if source.ref is None or "helm" in source.model_fields_set:
            raise ValueError(
                "Git sources must declare ref and supply only external values"
            )
        if source.ref in values_sources:
            raise ValueError(f"duplicate values source ref: {source.ref}")
        values_sources[source.ref] = source.repoURL
    values_files: list[Path] = []
    for entry in options.valueFiles:
        ref, separator, relative = entry.partition("/")
        if not ref.startswith("$") or not separator or not relative:
            raise ValueError("only external $ref/path values files are supported")
        root = repositories[values_sources[ref[1:]]].resolve()
        value_path = (root / relative).resolve()
        values_files.append(value_path)
    with TemporaryDirectory() as tmpdir:
        reference = (
            f"oci://{repository.removeprefix('oci://').rstrip('/')}/{chart_name}"
        )
        helm(
            "pull",
            reference,
            "--version",
            revision,
            "--untar",
            "--untardir",
            tmpdir,
            capture_stdout=True,
        )
        # Published chart packages already contain their dependencies. Rebuilding
        # can fail when their original file:// source directories are absent.
        chart_dir = Path(tmpdir) / chart_name
        return render_image_refs(
            HelmRender(
                chart=str(chart_dir),
                release=options.releaseName or document.name,
                namespace=document.namespace,
                values=tuple(values_files),
            )
        )


def discover_chart_image_refs(helm_dir: Path) -> set[str]:
    if not (helm_dir / CT_YAML).is_file():
        raise ClickException(f"{CT_YAML} is required in the root of --helm-dir")

    refs: set[str] = set()
    for chart_path in discover_charts(helm_dir):
        chart_dir = helm_dir / chart_path
        metadata = ChartMetadata.from_chart_dir(chart_dir)
        if metadata.type == "library":
            LOG.info("Skipping library chart: %s", chart_dir)
            continue

        prepare_chart_dependencies(chart_dir)
        values_files: Sequence[Path | None] = sorted(
            chart_dir.glob("ci/*-values.yaml")
        ) or (None,)
        for values_file in values_files:
            spec = HelmRender(
                chart=str(chart_dir),
                release="zep-pack",
                values=(values_file,) if values_file is not None else (),
            )
            refs.update(render_image_refs(spec))

        kind_values = chart_dir / "ci" / "kind-values.yaml"
        if kind_values.is_file():
            refs.update(extract_image_refs(kind_values.read_text(encoding="utf-8")))

    return refs


def discover_component_image_refs(components: ClusterComponents) -> set[str]:
    add_helm_repos(components, capture_stdout=True)
    refs: set[str] = set()
    for component in components.cluster_components:
        if not isinstance(component, ClusterComponent):
            LOG.warning("Skipping raw-manifest component: %s", component.name)
            continue
        chart_path = resolve_chart_path(component.chart, components.source_dir)
        if Path(chart_path).is_dir():
            prepare_chart_dependencies(Path(chart_path))
        spec = HelmRender(
            chart=chart_path,
            release=component.name,
            version=component.version,
            namespace=component.namespace,
            values=(component.values,) if component.values else (),
        )
        refs.update(render_image_refs(spec))
    return refs


def discover_pack_image_refs(
    helm_dir: Path | None = None,
    components: ClusterComponents | None = None,
    applications: Sequence[Path] = (),
    repositories: Mapping[str, Path] | None = None,
) -> list[str]:
    """Discover packable references without accessing a cluster or image engine."""
    refs = discover_chart_image_refs(helm_dir) if helm_dir is not None else set()
    if components is not None:
        refs.update(discover_component_image_refs(components))
    for application in applications:
        refs.update(discover_application_image_refs(application, repositories or {}))
    digest_refs = sorted(ref for ref in refs if "@" in ref)
    if digest_refs:
        LOG.warning(
            "This image archive implementation cannot preload digest references; skipping: %s",
            digest_refs,
        )
    return sorted(ref for ref in refs if is_tagged_image_ref(ref))


def pack_images(
    helm_dir: Path | None,
    output: Path,
    components: ClusterComponents | None = None,
    applications: Sequence[Path] = (),
    repositories: Mapping[str, Path] | None = None,
) -> None:
    selected = discover_pack_image_refs(
        helm_dir, components, applications, repositories
    )
    pack_image_refs(selected, output)


def pack_image_refs(selected: Sequence[str], output: Path) -> None:
    """Pull and save selected references without repeating discovery."""
    if not selected:
        LOG.warning("No packable image references found, not packing anything")
        return
    engine = choose_engine()
    LOG.info("Using container engine: %s", engine)
    pull_missing_images(engine, selected)
    save_image_archive(engine, output, selected)


def extract_image_refs(yaml_text: str) -> set[str]:
    refs: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if (
                    key in {"image", "imageName"}
                    and isinstance(child, str)
                    and child.strip()
                ):
                    refs.add(child.strip())
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for document in yaml.safe_load_all(yaml_text):
        visit(document)
    return refs


def pull_missing_images(engine: str, refs: Sequence[str]) -> None:
    for ref in refs:
        result = execute(
            engine,
            "image",
            "inspect",
            ref,
            capture_stdout=True,
            capture_stderr=True,
            skip_resolve=True,
            check=False,
        )
        if result.returncode != 0:
            LOG.info("Pulling image onto host: %s", ref)
            execute(engine, "pull", ref, capture_stdout=True, skip_resolve=True)


def save_image_archive(engine: str, output: Path, refs: Sequence[str]) -> None:
    for ref in refs:
        LOG.info("Including image: %s", ref)
    output.parent.mkdir(parents=True, exist_ok=True)
    save_options = (
        ["--multi-image-archive", "--format", "docker-archive"]
        if engine == "podman"
        else []
    )
    execute(
        engine,
        "save",
        *save_options,
        "-o",
        str(output),
        *refs,
        capture_stdout=True,
        skip_resolve=True,
    )
    LOG.info("Wrote image archive: %s", output)


def load_images(archive: Path) -> None:
    load_image_archive(archive)
