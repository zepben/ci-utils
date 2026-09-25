"""Render and apply CloudNativePG resources for a cluster component."""

import json
import logging
from typing import Any

import yaml

from zep_dev.k8s import kubectl
from zep_dev.models import CnpgComponent

LOG = logging.getLogger(__name__)


def cnpg_manifests(
    desired: CnpgComponent,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Render catalog/credentials/Cluster, then databases after Cluster Ready."""
    base = {"namespace": desired.namespace}
    initial: list[dict[str, Any]] = []
    spec = dict(desired.spec)
    if desired.image_catalog is not None:
        catalog_name = f"{desired.name}-image"
        initial.append(
            {
                "apiVersion": "postgresql.cnpg.io/v1",
                "kind": "ImageCatalog",
                "metadata": {"name": catalog_name, **base},
                "spec": {
                    "images": [
                        {
                            "major": desired.image_catalog.major,
                            "image": desired.image_catalog.image,
                        }
                    ]
                },
            }
        )
        spec["imageCatalogRef"] = {
            "apiGroup": "postgresql.cnpg.io",
            "kind": "ImageCatalog",
            "name": catalog_name,
            "major": desired.image_catalog.major,
        }
    secret_name = f"{desired.name}-app"
    initial.extend(
        [
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": secret_name, **base},
                "type": "kubernetes.io/basic-auth",
                "stringData": {"username": desired.owner, "password": desired.password},
            },
            {
                "apiVersion": "postgresql.cnpg.io/v1",
                "kind": "Cluster",
                "metadata": {"name": desired.name, **base},
                "spec": {
                    **spec,
                    "bootstrap": {
                        "initdb": {
                            "database": desired.database,
                            "owner": desired.owner,
                            "secret": {"name": secret_name},
                        }
                    },
                },
            },
        ]
    )
    databases = [
        {
            "apiVersion": "postgresql.cnpg.io/v1",
            "kind": "Database",
            "metadata": {"name": f"{desired.name}-{name}", **base},
            "spec": {
                "name": name,
                "owner": desired.owner,
                "cluster": {"name": desired.name},
                "extensions": [
                    {"name": ext, "ensure": "present"} for ext in database.extensions
                ],
            },
        }
        for name, database in desired.databases.items()
    ]
    return initial, databases


def apply_cnpg_component(desired: CnpgComponent) -> None:
    LOG.info("Applying CNPG cluster: %s", desired.name)
    initial, databases = cnpg_manifests(desired)
    for manifest in initial:
        kubectl("apply", "-f", "-", input=yaml.safe_dump(manifest))
    kubectl(
        "wait",
        "--for=condition=Ready",
        f"cluster/{desired.name}",
        f"--namespace={desired.namespace}",
        "--timeout=240s",
    )
    for manifest in databases:
        applied = kubectl(
            "apply",
            "-f",
            "-",
            "-o=json",
            input=yaml.safe_dump(manifest),
            capture_stdout=True,
        )
        generation = json.loads(applied.stdout)["metadata"]["generation"]
        database_resource = f"database/{manifest['metadata']['name']}"
        kubectl(
            "wait",
            f"--for=jsonpath={{.status.observedGeneration}}={generation}",
            database_resource,
            f"--namespace={desired.namespace}",
            "--timeout=180s",
        )
        kubectl(
            "wait",
            "--for=jsonpath={.status.applied}=true",
            database_resource,
            f"--namespace={desired.namespace}",
            "--timeout=180s",
        )
