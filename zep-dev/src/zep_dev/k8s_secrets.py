import logging
from pathlib import Path

from click import ClickException

from zep_dev.cluster import kubectl

IMAGE_SECRET_PATHS = [
    Path("~/.config/containers/auth.json").expanduser(),
    Path("~/.docker/config.json").expanduser(),
]
IMAGE_SECRET_NAME = "github-registry"

LOG = logging.getLogger(__name__)


def create_image_pull_secret(namespace: str) -> None:
    LOG.info("Creating imagePullSecret")
    auth_json_path = next((path for path in IMAGE_SECRET_PATHS if path.exists()), None)
    if auth_json_path is None:
        raise ClickException(
            f"Failed to locate auth.json to populate {IMAGE_SECRET_NAME} "
            f"at paths: {IMAGE_SECRET_PATHS}"
        )

    if not secret_exists(namespace=namespace, secret_name=IMAGE_SECRET_NAME):
        kubectl(
            "create",
            "secret",
            "generic",
            IMAGE_SECRET_NAME,
            f"--namespace={namespace}",
            f"--from-file=.dockerconfigjson={auth_json_path}",
            "--type=kubernetes.io/dockerconfigjson",
        )


def secret_exists(namespace: str, secret_name: str) -> bool:
    existing_secrets = kubectl(
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
