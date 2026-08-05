import logging
from pathlib import Path

from click import ClickException

from zep_dev.k8s import kubectl, resource_exists

IMAGE_SECRET_PATHS = [
    Path("~/.config/containers/auth.json").expanduser(),
    Path("~/.docker/config.json").expanduser(),
]
IMAGE_SECRET_NAME = "github-registry"

LOG = logging.getLogger(__name__)


def create_image_pull_secret(namespace: str) -> None:
    if not resource_exists("namespace", namespace):
        raise ClickException(f"Namespace does not exist: {namespace}")
    LOG.info("Creating imagePullSecret")
    auth_json_path = next((path for path in IMAGE_SECRET_PATHS if path.exists()), None)
    if auth_json_path is None:
        raise ClickException(
            f"Failed to locate auth.json to populate {IMAGE_SECRET_NAME} "
            f"at paths: {IMAGE_SECRET_PATHS}"
        )

    if not resource_exists("secret", IMAGE_SECRET_NAME, namespace=namespace):
        kubectl(
            "create",
            "secret",
            "generic",
            IMAGE_SECRET_NAME,
            f"--namespace={namespace}",
            f"--from-file=.dockerconfigjson={auth_json_path}",
            "--type=kubernetes.io/dockerconfigjson",
        )
