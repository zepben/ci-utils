"""Translate consumed local checkouts into Kind mounts and Argo values."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import NotRequired, TypedDict

from zep_dev.development_environments.kind import HostMount

LOCAL_REPO_MOUNT_ROOT = "/mnt/local-repos"


class LocalRepository(TypedDict):
    name: str
    type: str
    url: str


class ArgoConfigs(TypedDict):
    repositories: dict[str, LocalRepository]


class RepositoryVolumeMount(TypedDict):
    name: str
    mountPath: str
    readOnly: bool


class HostPath(TypedDict):
    path: str
    type: str


class RepositoryVolume(TypedDict):
    name: str
    hostPath: HostPath


class RepoServerOverlay(TypedDict):
    affinity: dict[str, object]
    env: list[dict[str, str]]
    volumeMounts: list[RepositoryVolumeMount]
    volumes: list[RepositoryVolume]


class ArgoOverlay(TypedDict):
    configs: NotRequired[ArgoConfigs]
    repoServer: NotRequired[RepoServerOverlay]


def repository_mounts(repositories: Mapping[str, Path]) -> tuple[HostMount, ...]:
    return tuple(
        HostMount(path, f"{LOCAL_REPO_MOUNT_ROOT}/{path.name}", read_only=True)
        for path in repositories.values()
    )


def repository_overlay(repositories: Sequence[Path]) -> ArgoOverlay:
    if not repositories:
        return {}
    return {
        "configs": {
            "repositories": {
                f"local-{path.name}": {
                    "name": path.name,
                    "type": "git",
                    "url": f"file://{LOCAL_REPO_MOUNT_ROOT}/{path.name}",
                }
                for path in repositories
            }
        },
        "repoServer": {
            "affinity": {
                "nodeAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": {
                        "nodeSelectorTerms": [
                            {
                                "matchExpressions": [
                                    {
                                        "key": "node-role.kubernetes.io/control-plane",
                                        "operator": "DoesNotExist",
                                    }
                                ]
                            }
                        ]
                    }
                }
            },
            "env": [
                {"name": "GIT_CONFIG_COUNT", "value": "1"},
                {"name": "GIT_CONFIG_KEY_0", "value": "safe.directory"},
                {"name": "GIT_CONFIG_VALUE_0", "value": "*"},
            ],
            "volumeMounts": [
                {
                    "name": "local-repos",
                    "mountPath": LOCAL_REPO_MOUNT_ROOT,
                    "readOnly": True,
                }
            ],
            "volumes": [
                {
                    "name": "local-repos",
                    "hostPath": {"path": LOCAL_REPO_MOUNT_ROOT, "type": "Directory"},
                }
            ],
        },
    }
