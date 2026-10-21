"""CNPG resource generation and readiness for an Environment."""

from typing import TypedDict

import yaml

from zep_dev.development_environments.kubernetes import KubernetesObject, kubectl
from zep_dev.development_environments.services import CnpgService
from zep_dev.development_environments.target import ExecutionTarget


class DatabaseConnection(TypedDict):
    host: str
    port: int
    name: str
    username: str
    password: str


def cnpg_manifests(
    target: ExecutionTarget, name: str, service: CnpgService
) -> tuple[list[KubernetesObject], list[KubernetesObject]]:
    namespace = service.namespace or target.namespace
    initial: list[KubernetesObject] = []
    spec = dict(service.spec)
    if service.image_catalog is not None:
        catalog_name = f"{name}-image"
        initial.append(
            {
                "apiVersion": "postgresql.cnpg.io/v1",
                "kind": "ImageCatalog",
                "metadata": {"name": catalog_name, "namespace": namespace},
                "spec": {
                    "images": [
                        {
                            "major": service.image_catalog.major,
                            "image": service.image_catalog.image,
                        }
                    ]
                },
            }
        )
        spec["imageCatalogRef"] = {
            "apiGroup": "postgresql.cnpg.io",
            "kind": "ImageCatalog",
            "name": catalog_name,
            "major": service.image_catalog.major,
        }
    secret_name = f"{name}-app"
    initial.extend(
        [
            {
                "apiVersion": "v1",
                "kind": "Secret",
                "metadata": {"name": secret_name, "namespace": namespace},
                "type": "kubernetes.io/basic-auth",
                "stringData": {
                    "username": service.owner,
                    "password": service.password,
                },
            },
            {
                "apiVersion": "postgresql.cnpg.io/v1",
                "kind": "Cluster",
                "metadata": {"name": name, "namespace": namespace},
                "spec": {
                    **spec,
                    "bootstrap": {
                        "initdb": {
                            "database": service.database,
                            "owner": service.owner,
                            "secret": {"name": secret_name},
                        }
                    },
                },
            },
        ]
    )
    databases: list[KubernetesObject] = [
        {
            "apiVersion": "postgresql.cnpg.io/v1",
            "kind": "Database",
            "metadata": {"name": f"{name}-{database_name}", "namespace": namespace},
            "spec": {
                "name": database_name,
                "owner": service.owner,
                "cluster": {"name": name},
                "extensions": [
                    {"name": extension, "ensure": "present"}
                    for extension in database.extensions
                ],
            },
        }
        for database_name, database in service.databases.items()
    ]
    return initial, databases


def apply_cnpg_service(
    target: ExecutionTarget, name: str, service: CnpgService
) -> None:
    initial, databases = cnpg_manifests(target, name, service)
    for manifest in initial:
        kubectl(
            target,
            "apply",
            "-f",
            "-",
            input=yaml.safe_dump(manifest),
            sensitive=manifest["kind"] == "Secret",
        )
    namespace = service.namespace or target.namespace
    kubectl(
        target,
        "wait",
        "--for=condition=Ready",
        f"cluster/{name}",
        f"--namespace={namespace}",
        "--timeout=240s",
    )
    for manifest in databases:
        apply_database_and_wait(target, namespace, manifest)


def apply_database_and_wait(
    target: ExecutionTarget, namespace: str, manifest: KubernetesObject
) -> None:
    kubectl(
        target,
        "apply",
        "-f",
        "-",
        input=yaml.safe_dump(manifest),
    )
    kubectl(
        target,
        "wait",
        "--for=jsonpath={.status.applied}=true",
        f"database/{manifest['metadata']['name']}",
        f"--namespace={namespace}",
        "--timeout=180s",
    )
