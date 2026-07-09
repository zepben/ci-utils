from contextlib import chdir
from pathlib import Path
from subprocess import CalledProcessError

import click
from click import ClickException

from local_k8s.shared import execute

CT_YAML = "ct.yaml"


@click.command("lint-and-install")
@click.option(
    "--helm-dir",
    type=click.Path(
        exists=True,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    required=True,
)
def lint_and_install(helm_dir: Path) -> None:
    with chdir(helm_dir.absolute()):
        ct_yaml_path = Path(CT_YAML)
        if not ct_yaml_path.exists():
            raise ClickException("ct.yaml is required in the root of --helm-dir")
        try:
            execute(
                "ct",
                "lint-and-install",
                "--config",
                "ct.yaml",
                "--all",
                "--check-version-increment=false",
                capture_stdout=False,
            )
        except CalledProcessError as e:
            raise ClickException(
                f"lint-and-install failed with rc={e.returncode}"
            ) from e
