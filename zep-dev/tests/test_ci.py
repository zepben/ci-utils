import json
from unittest.mock import MagicMock

import pytest
import requests

from zep_dev import ci

BASE_URL = "https://api.github.com/repos/zepben/example/actions"


def response(
    body: object, *, status: int = 200, next_page: bool = False
) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(body).encode()
    if next_page:
        result.headers["Link"] = f'<{BASE_URL}/artifacts?page=2>; rel="next"'
    return result


def artifact(identifier: int, **provenance: int) -> dict[str, object]:
    return {
        "id": identifier,
        "created_at": f"2026-10-{identifier:02d}T00:00:00Z",
        "expired": False,
        "workflow_run": {
            "id": 100 + identifier,
            "repository_id": 10,
            "head_repository_id": 10,
            **provenance,
        },
    }


@pytest.fixture
def github(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    session = MagicMock(spec=requests.Session)
    session.headers = {}
    session.__enter__.return_value = session
    session.get.side_effect = [
        response({"workflow_id": 20, "repository": {"id": 10}}),
        response({"artifacts": []}),
    ]
    monkeypatch.setattr(ci.requests, "Session", lambda: session)
    return session


def test_selects_newest_eligible_artifact_across_pages(github: MagicMock) -> None:
    expired = artifact(6)
    expired["expired"] = True
    github.get.side_effect = [
        response({"workflow_id": 20, "repository": {"id": 10}}),
        response(
            {
                "artifacts": [
                    artifact(1),
                    artifact(5, head_repository_id=99),
                    artifact(3),
                ]
            },
            next_page=True,
        ),
        response(
            {
                "artifacts": [
                    expired,
                    artifact(2),
                    artifact(7, repository_id=99),
                    artifact(4),
                ]
            }
        ),
        response({"workflow_id": 99, "event": "pull_request"}),
        response({"workflow_id": 20, "event": "schedule"}),
        response({"workflow_id": 20, "event": "pull_request", "conclusion": "failure"}),
    ]

    assert ci.find_cached_image_archive(
        "zepben/example", 100, "kind-images-v1-linux-amd64-hash"
    ) == {"artifact_id": 2, "run_id": 102}


def test_empty_search_returns_none(github: MagicMock) -> None:
    assert (
        ci.find_cached_image_archive(
            "zepben/example", 100, "kind-images-v1-linux-amd64-hash"
        )
        is None
    )


def test_lookup_failure_is_not_a_cache_miss(github: MagicMock) -> None:
    github.get.side_effect = [
        response({"workflow_id": 20, "repository": {"id": 10}}),
        response({"artifacts": [artifact(1)]}),
        response({}, status=403),
    ]

    with pytest.raises(requests.HTTPError):
        ci.find_cached_image_archive(
            "zepben/example", 100, "kind-images-v1-linux-amd64-hash"
        )
