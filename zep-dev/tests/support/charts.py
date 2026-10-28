import io
import tarfile
from pathlib import Path

import yaml

from tests.support.execution import ExecuteHook, option_value


def write_chart(chart_dir: Path, chart_yaml: dict[str, object]) -> Path:
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "Chart.yaml").write_text(yaml.dump(chart_yaml))
    return chart_dir


def pull_annotated_chart_package(annotations: dict[str, str]) -> ExecuteHook:
    """Fake `helm pull`: write a chart package with annotations to --destination."""

    def pull(args: tuple[str, ...], _kwargs: dict[str, object]) -> None:
        name = args[2].rsplit("/", 1)[1]
        version = option_value(args, "--version")
        chart_yaml = {"name": name, "version": version, "annotations": annotations}
        content = yaml.safe_dump(chart_yaml).encode()
        member = tarfile.TarInfo(f"{name}/Chart.yaml")
        member.size = len(content)
        package = Path(option_value(args, "--destination")) / f"{name}-{version}.tgz"
        with tarfile.open(package, "w:gz") as archive:
            archive.addfile(member, io.BytesIO(content))

    return pull


pull_chart_package = pull_annotated_chart_package({})
