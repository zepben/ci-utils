import io
import tarfile
from pathlib import Path

import yaml

from tests.support.execution import option_value


def write_chart(chart_dir: Path, chart_yaml: dict[str, object]) -> Path:
    chart_dir.mkdir(parents=True, exist_ok=True)
    (chart_dir / "Chart.yaml").write_text(yaml.dump(chart_yaml))
    return chart_dir


def pull_chart_package(args: tuple[str, ...], _kwargs: dict[str, object]) -> None:
    """Fake `helm pull`: write a chart package to --destination."""
    name = args[2].rsplit("/", 1)[1]
    version = option_value(args, "--version")
    content = yaml.safe_dump({"name": name, "version": version}).encode()
    member = tarfile.TarInfo(f"{name}/Chart.yaml")
    member.size = len(content)
    package = Path(option_value(args, "--destination")) / f"{name}-{version}.tgz"
    with tarfile.open(package, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(content))
