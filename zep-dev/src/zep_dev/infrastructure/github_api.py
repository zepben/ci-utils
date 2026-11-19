import os
import re

import requests
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from zep_dev.errors import ZepDevError

_SHA = re.compile(r"[0-9a-f]{40}\Z")
_WORKFLOW = "build-commit-container.yaml"


class _Repository(BaseModel):
    model_config = ConfigDict(strict=True)
    full_name: str


class _PullRequestHead(BaseModel):
    model_config = ConfigDict(strict=True)
    sha: str
    repo: _Repository


class _PullRequest(BaseModel):
    model_config = ConfigDict(strict=True)
    head: _PullRequestHead


class PullRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    number: int
    title: str
    body: str | None = None
    html_url: str
    merged_at: str | None = None
    merge_commit_sha: str | None = None


_COMMIT_PULL_REQUESTS = TypeAdapter(list[PullRequest])


class GitHubAPI:
    def __init__(self, base_url: str = "https://api.github.com") -> None:
        self.base_url = base_url

    @staticmethod
    def token() -> str:
        token = os.environ.get("GH_TOKEN", "").strip()
        if not token:
            raise ZepDevError("GH_TOKEN is required for GitHub API access")
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
            raise ZepDevError(
                f"GitHub API {kind} error: HTTP {response.status_code} for {path}"
            )
        return response

    def pr_head(self, repo_name: str, number: int) -> str:
        response = self.request("GET", f"/repos/zepben/{repo_name}/pulls/{number}")
        try:
            head = _PullRequest.model_validate_json(response.text).head
        except ValidationError as error:
            raise RuntimeError(f"Invalid head response for PR #{number}") from error
        sha = head.sha
        source = head.repo.full_name
        if source.lower() != f"zepben/{repo_name}".lower():
            raise ZepDevError(
                f"PR #{number} comes from a fork; refusing privileged build"
            )
        if not _SHA.fullmatch(sha):
            raise RuntimeError(f"Invalid head SHA for PR #{number}")
        return sha

    def merged_pull_request(self, repository: str, sha: str) -> PullRequest | None:
        """The pull request merged as this commit; None for a direct push."""
        response = self.request("GET", f"/repos/{repository}/commits/{sha}/pulls")
        try:
            pulls = _COMMIT_PULL_REQUESTS.validate_json(response.text)
        except ValidationError as error:
            raise RuntimeError(
                f"Invalid pull request response for commit {sha}"
            ) from error
        return next(
            (pull for pull in pulls if pull.merged_at and pull.merge_commit_sha == sha),
            None,
        )

    def dispatch_build(self, repo_name: str, default_branch: str, sha: str) -> None:
        self.request(
            "POST",
            f"/repos/zepben/{repo_name}/actions/workflows/{_WORKFLOW}/dispatches",
            {"ref": default_branch, "inputs": {"commit": sha}},
        )
