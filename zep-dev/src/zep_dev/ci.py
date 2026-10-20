import logging
import os
from hashlib import sha256
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import requests

from zep_dev import cluster_images
from zep_dev.cluster import require_nonempty_image_archive
from zep_dev.models import ClusterComponents, ImageDiscoveryConfig

LOG = logging.getLogger(__name__)


def prepare_image_archive(
    config: Path,
    repository: str,
    run_id: int,
    bundle: str,
    temp_dir: Path,
) -> dict[str, str]:
    discovery = ImageDiscoveryConfig.from_path(config)
    components = (
        ClusterComponents.from_path(discovery.components)
        if discovery.components is not None
        else None
    )
    refs = cluster_images.discover_pack_image_refs(
        discovery.helm_dir, components, discovery.applications, discovery.repositories
    )
    if not refs:
        LOG.info("No image requirements discovered.")
        return {"result": "empty"}

    manifest = "".join(f"{ref}\n" for ref in refs).encode("utf-8")
    name = f"{bundle}-linux-amd64-{sha256(manifest).hexdigest()}"
    LOG.info("Image artifact: %s", name)
    LOG.info("Image requirements:\n%s", manifest.decode("utf-8").rstrip())
    cached = find_cached_image_archive(repository, run_id, name)
    directory = Path(mkdtemp(prefix="kind-images.", dir=temp_dir)).resolve()
    archive = directory / "images.tar"
    outputs = {
        "directory": str(directory),
        "name": name,
        "archive-path": str(archive),
    }
    if cached is not None:
        outputs.update(
            {
                "result": "hit",
                "artifact-id": str(cached["artifact_id"]),
                "run-id": str(cached["run_id"]),
            }
        )
        LOG.info(
            "Image cache hit: artifact %s, run %s.",
            cached["artifact_id"],
            cached["run_id"],
        )
    else:
        LOG.info("Image cache miss; packing images.")
        (directory / "images.txt").write_bytes(manifest)
        cluster_images.pack_image_refs(refs, archive)
        require_nonempty_image_archive(archive)
        LOG.info("Image archive size: %s bytes", archive.stat().st_size)
        outputs.update({"result": "miss", "run-id": str(run_id)})
    return outputs


def find_cached_image_archive(
    repository: str, run_id: int, name: str
) -> dict[str, int] | None:
    base_url = f"https://api.github.com/repos/{repository}/actions"
    with requests.Session() as session:
        session.headers.update(
            {
                "Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2026-03-10",
            }
        )

        def get_run(identifier: int) -> dict[str, Any]:
            response = session.get(f"{base_url}/runs/{identifier}", timeout=30)
            response.raise_for_status()
            result: dict[str, Any] = response.json()
            return result

        current = get_run(run_id)
        workflow_id = current["workflow_id"]
        repository_id = current["repository"]["id"]
        candidates: list[dict[str, Any]] = []
        page = 1
        while True:
            response = session.get(
                f"{base_url}/artifacts",
                params={"name": name, "per_page": "100", "page": str(page)},
                timeout=30,
            )
            response.raise_for_status()
            candidates.extend(
                artifact
                for artifact in response.json()["artifacts"]
                if not artifact["expired"]
            )
            if "next" not in response.links:
                break
            page += 1

        for artifact in sorted(
            candidates, key=lambda artifact: artifact["created_at"], reverse=True
        ):
            provenance = artifact["workflow_run"]
            if provenance["head_repository_id"] != repository_id:
                continue
            if provenance["repository_id"] != repository_id:
                continue
            producer_id = provenance["id"]
            producer = get_run(producer_id)
            if producer["workflow_id"] != workflow_id:
                continue
            if producer["event"] not in {"pull_request", "workflow_dispatch"}:
                continue
            return {"artifact_id": artifact["id"], "run_id": producer_id}
    return None
