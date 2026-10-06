import os
import re

import requests

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_WORKFLOW = "build-commit-container.yaml"


class GitHubAPI:
    def __init__(self, base_url: str = "https://api.github.com") -> None:
        self.base_url = base_url

    @staticmethod
    def token() -> str:
        token = os.environ.get("GH_TOKEN", "").strip()
        if not token:
            raise RuntimeError("GH_TOKEN is required for PR lookup and build dispatch")
        return token

    def request(
        self, method: str, path: str, payload: dict[str, object] | None = None
    ) -> requests.Response:
        response = requests.request(
            method,
            f"{self.base_url}{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token()}",
            },
            timeout=20,
            json=payload,
        )
        if not response.ok:
            kind = "authentication" if response.status_code in (401, 403) else "request"
            raise RuntimeError(
                f"GitHub API {kind} error: HTTP {response.status_code} for {path}"
            )
        return response

    def pr_head(self, repo_name: str, number: int) -> str:
        response = self.request("GET", f"/repos/zepben/{repo_name}/pulls/{number}")
        head = response.json()["head"]
        sha = head["sha"]
        source = head["repo"]["full_name"]
        if not isinstance(source, str):
            raise RuntimeError(f"Invalid source repository for PR #{number}")
        if source.lower() != f"zepben/{repo_name}".lower():
            raise ValueError(
                f"PR #{number} comes from a fork; refusing privileged build"
            )
        if not isinstance(sha, str) or not _SHA.fullmatch(sha):
            raise RuntimeError(f"Invalid head SHA for PR #{number}")
        return sha

    def dispatch_build(self, repo_name: str, default_branch: str, sha: str) -> None:
        self.request(
            "POST",
            f"/repos/zepben/{repo_name}/actions/workflows/{_WORKFLOW}/dispatches",
            {"ref": default_branch, "inputs": {"commit": sha}},
        )
