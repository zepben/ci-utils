import json

import pytest
import requests

from zep_dev.infrastructure.github_api import GitHubAPI

SHA = "a" * 40


def test_dispatch_payload_uses_default_branch_and_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    sent: list[tuple[str, str, dict[str, object]]] = []

    def request(method: str, url: str, **kwargs: object) -> requests.Response:
        sent.append((method, url, kwargs))
        response = requests.Response()
        response.status_code = 204
        return response

    monkeypatch.setattr(requests, "request", request)

    GitHubAPI().dispatch_build("energy-workbench-server", "main", SHA)

    assert len(sent) == 1
    method, url, kwargs = sent[0]
    assert method == "POST"
    assert url == (
        "https://api.github.com/repos/zepben/energy-workbench-server"
        "/actions/workflows/build-commit-container.yaml/dispatches"
    )
    assert kwargs["json"] == {"ref": "main", "inputs": {"commit": SHA}}


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"head": None},
        {"head": {"sha": SHA, "repo": None}},
        {"head": {"sha": SHA, "repo": {"full_name": 123}}},
        {"head": {"sha": 123, "repo": {"full_name": "zepben/energy-workbench-server"}}},
    ],
    ids=[
        "not-a-mapping",
        "missing-head",
        "deleted-repository",
        "invalid-repository",
        "invalid-sha-type",
    ],
)
def test_pr_response_rejects_invalid_structure(
    monkeypatch: pytest.MonkeyPatch, payload: object
) -> None:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="Invalid head response for PR #42"):
        GitHubAPI().pr_head("energy-workbench-server", 42)


@pytest.mark.parametrize(
    ("merge_sha", "merged_at", "expected"),
    [
        (SHA, "2026-11-18T00:00:00Z", 42),
        (SHA, None, None),
        ("b" * 40, "2026-11-18T00:00:00Z", None),
    ],
)
def test_commit_lookup_selects_only_the_pull_request_merged_as_that_commit(
    monkeypatch: pytest.MonkeyPatch,
    merge_sha: str,
    merged_at: str | None,
    expected: int | None,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(
        [
            {
                "number": 42,
                "title": "Feature",
                "body": None,
                "html_url": "https://github.com/zepben/commons/pull/42",
                "merge_commit_sha": merge_sha,
                "merged_at": merged_at,
            }
        ]
    ).encode()
    sent: list[str] = []

    def request(method: str, url: str, **kwargs: object) -> requests.Response:
        assert method == "GET"
        assert kwargs["headers"] == {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer test-token",
        }
        sent.append(url)
        return response

    monkeypatch.setattr(requests, "request", request)
    pull = GitHubAPI().merged_pull_request("zepben/commons", SHA)

    assert (pull.number if pull is not None else None) == expected
    assert sent == [f"https://api.github.com/repos/zepben/commons/commits/{SHA}/pulls"]


def test_commit_lookup_rejects_invalid_api_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "test-token")
    response = requests.Response()
    response.status_code = 200
    response._content = b'{"message": "not a pull request list"}'
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)

    with pytest.raises(RuntimeError, match="Invalid pull request response"):
        GitHubAPI().merged_pull_request("zepben/commons", SHA)
