from contextlib import chdir
from pathlib import Path
from subprocess import CalledProcessError

import click
import yaml
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
            raise ClickException(f"{CT_YAML} is required in the root of --helm-dir")

        create_test_namespace(ct_yaml_path)
        execute_lint_and_install()


def create_test_namespace(ct_yaml_path: Path) -> None:
    ct_yaml = yaml.safe_load(ct_yaml_path.read_text())
    test_namespace = ct_yaml.get("namespace")
    if test_namespace is None:
        raise ClickException(f"namespace must be specified in {CT_YAML}")
    namespaces = execute("kubectl", "get", "namespaces")
    for line in namespaces.splitlines():
        ns, *_ = line.split()
        if ns == test_namespace:
            break
    else:
        execute("kubectl", "create", "namespace", test_namespace)


def execute_lint_and_install() -> None:
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
        raise ClickException(f"lint-and-install failed with rc={e.returncode}") from e
