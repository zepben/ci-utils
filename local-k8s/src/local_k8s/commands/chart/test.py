import logging
from contextlib import chdir
from pathlib import Path
from subprocess import CalledProcessError

import click
import yaml
from click import ClickException
from pydantic import ValidationError

from local_k8s.models import ChartMetadata, CiSecrets
from local_k8s.shared import ResolvedChart, execute, resolve_chart
from local_k8s.static import CI_SECRETS_YAML, CT_YAML

IMAGE_SECRET_PATHS = [
    Path("~/.config/containers/auth.json").expanduser(),
    Path("~/.docker/config.json").expanduser(),
]
IMAGE_SECRET_NAME = "github-registry"

LOG = logging.getLogger(__name__)


@click.command("test")
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
@click.option(
    "--chart",
    type=click.Path(
        exists=False,
        file_okay=False,
        dir_okay=True,
        path_type=Path,
    ),
    default=None,
)
def test(helm_dir: Path, chart: Path | None) -> None:
    helm_dir = helm_dir.resolve()
    if not (helm_dir / CT_YAML).is_file():
        raise ClickException(f"{CT_YAML} is required in the root of --helm-dir")

    if chart is not None:
        resolved_charts = [resolve_chart(helm_dir, chart)]
    else:
        resolved_charts = [
            ResolvedChart(
                absolute_path=helm_dir / discovered_chart,
                path_relative_to_helm_dir=discovered_chart,
            )
            for discovered_chart in discover_charts(helm_dir)
        ]

    with chdir(helm_dir):
        namespace = create_test_namespace(CT_YAML)
        create_secrets(namespace=namespace)

        for resolved_chart in resolved_charts:
            test_chart(resolved_chart)


def discover_charts(helm_dir: Path) -> list[Path]:
    return sorted(
        p.parent.relative_to(helm_dir) for p in helm_dir.glob("charts/*/Chart.yaml")
    )


def test_chart(resolved_chart: ResolvedChart) -> None:
    try:
        meta = ChartMetadata.from_chart_dir(resolved_chart.absolute_path)
    except (ValueError, ValidationError) as e:
        raise ClickException(str(e)) from e

    if meta.type == "library":
        click.echo(f"Skipping install for library chart: {meta.name}")
        return

    execute_lint_and_install(CT_YAML, resolved_chart.path_relative_to_helm_dir)


def create_test_namespace(ct_yaml_path: Path) -> str:
    ct_yaml = yaml.safe_load(ct_yaml_path.read_text())
    test_namespace: str | None = ct_yaml.get("namespace")
    if test_namespace is None:
        raise ClickException(f"namespace must be specified in {CT_YAML}")
    namespaces = execute("kubectl", "get", "namespaces", capture_stdout=True)
    for line in namespaces.stdout.splitlines():
        ns, *_ = line.split()
        if ns == test_namespace:
            break
    else:
        execute("kubectl", "create", "namespace", test_namespace)
    return test_namespace


def create_secrets(namespace: str) -> None:
    create_additional_secrets(namespace)
    create_image_pull_secret(namespace)


def create_additional_secrets(namespace: str) -> None:
    """
    If an Application requires additional secrets, it can place a file "ci-secrets.yaml" next to ct.yaml
    in the helm dir. This file defines where to locate additional secrets that need to be injected into
    Kubernetes in order for the tests to success. As an example, the EWB requires AWS access creds to download
    an empty network model for it to be able to successfully start up and allow the helm unit test probes
    to pass successfully.
    """
    if CI_SECRETS_YAML.exists():
        config = CiSecrets.model_validate(yaml.safe_load(CI_SECRETS_YAML.read_text()))
        for secret in config.secrets:
            LOG.info("Creating additional secret: %s", secret.name)
            secret_path = secret.resolve_path()
            if not secret_path.is_file():
                raise ClickException(
                    f"Secret {secret.name}:{secret.env_var} "
                    f"points to non-existent path: {secret_path}"
                )
            if not secret_exists(namespace=namespace, secret_name=secret.name):
                execute(
                    "kubectl",
                    f"--namespace={namespace}",
                    "create",
                    "secret",
                    "generic",
                    secret.name,
                    f"--from-env-file={secret_path}",
                )


def create_image_pull_secret(namespace: str) -> None:
    LOG.info("Creating imagePullSecret")
    auth_json_path = next((path for path in IMAGE_SECRET_PATHS if path.exists()), None)
    if auth_json_path is None:
        raise ClickException(
            f"Failed to locate auth.json to populate {IMAGE_SECRET_NAME} "
            f"at paths: {IMAGE_SECRET_PATHS}"
        )

    if not secret_exists(namespace=namespace, secret_name=IMAGE_SECRET_NAME):
        execute(
            "kubectl",
            "create",
            "secret",
            "generic",
            IMAGE_SECRET_NAME,
            f"--namespace={namespace}",
            f"--from-file=.dockerconfigjson={auth_json_path}",
            "--type=kubernetes.io/dockerconfigjson",
        )


def secret_exists(namespace: str, secret_name: str) -> bool:
    existing_secrets = execute(
        "kubectl",
        "get",
        "secrets",
        f"--namespace={namespace}",
        "--no-headers",
        capture_stdout=True,
    )
    for line in existing_secrets.stdout.splitlines():
        existing_secret, *_ = line.split()
        if existing_secret == secret_name:
            return True
    return False


def execute_lint_and_install(
    ct_yaml_path: Path, chart_path_relative_to_helm_dir: Path
) -> None:
    try:
        execute(
            "ct",
            "lint-and-install",
            "--config",
            str(ct_yaml_path),
            "--charts",
            str(chart_path_relative_to_helm_dir),
            "--check-version-increment=true",
        )
    except CalledProcessError as e:
        raise ClickException(f"lint-and-install failed with rc={e.returncode}") from e
