import pytest
import requests

from zep_dev.github_api import GitHubAPI

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
    import json

    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(payload).encode()
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="Invalid head response for PR #42"):
        GitHubAPI().pr_head("energy-workbench-server", 42)
