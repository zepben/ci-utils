import base64
import json
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


def resolve_registry_credential(registry: str) -> tuple[str, str]:
    try:
        for path in IMAGE_SECRET_PATHS:
            if not path.is_file():
                continue
            entry = json.loads(path.read_text(encoding="utf-8"))["auths"].get(registry)
            if entry is None:
                continue
            decoded = base64.b64decode(entry["auth"], validate=True).decode("utf-8")
            username, password = decoded.split(":", 1)
            if not username or not password:
                raise ValueError("credential contains an empty username or password")
            return username, password
        raise LookupError("credential was not found in local container auth")
    except Exception as error:
        raise ClickException(
            f"Failed to resolve local credential for {registry}: {type(error).__name__}"
        ) from error


def create_image_pull_secret(namespace: str) -> None:
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
