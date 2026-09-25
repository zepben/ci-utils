"""Distribution source resolution, polling, and GitHub API behavior."""

import time
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests
import yaml
from click.testing import CliRunner

from zep_dev import github_api, source_chart
from zep_dev.cli import cli
from zep_dev.commands.distribution import build as build_module
from zep_dev.commands.distribution.build import ensure_source_chart
from zep_dev.distribution import CommitLocator, PullRequestLocator
from zep_dev.git_cache import REPOSITORIES, GitCache
from zep_dev.github_api import GitHubAPI

SHA = "a" * 40


@dataclass
class FakeCache(GitCache):
    repo: Path
    events: list[tuple[object, ...]]

    def ensure_repo(self, name: str) -> Path:
        self.events.append(("ensure_repo", name))
        return self.repo

    def pr_head_commit(self, repo: Path, number: int, expected: str) -> str:
        self.events.append(("pr_head_commit", repo, number, expected))
        return SHA

    def trusted_commit(self, repo: Path, sha: str) -> str:
        self.events.append(("trusted_commit", repo, sha))
        return sha

    def default_branch(self, repo: Path) -> str:
        self.events.append(("default_branch", repo))
        return "main"


@dataclass
class FakeAPI(GitHubAPI):
    events: list[tuple[object, ...]]
    pr_error: BaseException | None = None
    dispatched: list[tuple[str, str, str]] = field(default_factory=list)

    def pr_head(self, repo_name: str, number: int) -> str:
        self.events.append(("pr_head", repo_name, number))
        if self.pr_error is not None:
            raise self.pr_error
        return SHA

    def dispatch_build(self, repo_name: str, branch: str, sha: str) -> None:
        self.dispatched.append((repo_name, branch, sha))


@pytest.fixture
def services(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[FakeCache, FakeAPI, list[tuple[object, ...]]]:
    events: list[tuple[object, ...]] = []
    cache = FakeCache(tmp_path / "cache", events)
    api = FakeAPI(events)
    monkeypatch.setattr(build_module, "GitCache", lambda: cache)
    monkeypatch.setattr(build_module, "GitHubAPI", lambda: api)
    monkeypatch.setattr(
        source_chart, "calculate_chart_version", lambda repo, sha: "1.2.3"
    )
    monkeypatch.setattr(build_module, "require_ghcr_credentials", lambda: None)
    return cache, api, events


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    current = [0.0]
    monkeypatch.setattr(time, "monotonic", lambda: current[0])
    monkeypatch.setattr(
        time, "sleep", lambda seconds: current.__setitem__(0, current[0] + seconds)
    )
    return current


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        (PullRequestLocator(pullRequest=42), ("pr_head_commit", 42, SHA)),
        (CommitLocator(commit=SHA), ("trusted_commit", SHA)),
    ],
)
def test_source_locators_resolve_frozen_sha_without_dispatch(
    services: tuple[FakeCache, FakeAPI, list[tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
    locator: PullRequestLocator | CommitLocator,
    expected: tuple[object, ...],
    capsys: pytest.CaptureFixture[str],
) -> None:
    cache, api, events = services
    monkeypatch.setattr(build_module, "probe_oci_chart", lambda *args, **kw: True)

    ensure_source_chart("ewb", locator, cache, api)

    assert (expected[0], cache.repo, *expected[1:]) in events
    assert api.dispatched == []
    assert f"resolved ewb: {SHA} -> 1.2.3" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("locator", "event"),
    [
        ({"pullRequest": 42}, "pr_head_commit"),
        ({"commit": SHA}, "trusted_commit"),
    ],
)
def test_cli_keeps_pr_and_commit_on_oci_path(
    tmp_path: Path,
    services: tuple[FakeCache, FakeAPI, list[tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
    locator: dict[str, object],
    event: str,
) -> None:
    _cache, api, events = services
    path = tmp_path / "distribution.yaml"
    path.write_text(
        yaml.safe_dump({"metadata": {"name": "demo"}, "components": {"ewb": locator}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(build_module, "probe_oci_chart", lambda *args, **kw: True)

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code == 0, result.output
    assert any(item[0] == event for item in events)
    assert api.dispatched == []


def test_commit_timeout_reports_frozen_sha_and_progress(
    services: tuple[FakeCache, FakeAPI, list[tuple[object, ...]]],
    clock: list[float],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cache, api, _ = services
    monkeypatch.setattr(build_module, "probe_oci_chart", lambda *args, **kw: False)

    with pytest.raises(TimeoutError, match=f"{SHA}.*check .*actions"):
        ensure_source_chart(
            "ewb",
            CommitLocator(commit=SHA),
            cache,
            api,
        )

    output = capsys.readouterr().out
    assert "waiting for ewb:1.2.3 (5m elapsed)" in output
    assert "waiting for ewb:1.2.3 (55m elapsed)" in output
    assert clock[0] == 3600


def test_poll_wait_is_capped_by_deadline(
    services: tuple[FakeCache, FakeAPI, list[tuple[object, ...]]],
    clock: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, api, _ = services
    calls = [0]

    def probe(*args: object, **kwargs: object) -> bool:
        calls[0] += 1
        if calls[0] == 1:
            return False
        clock[0] = 3590
        return False

    monkeypatch.setattr(build_module, "probe_oci_chart", probe)
    with pytest.raises(TimeoutError, match="Timed out"):
        ensure_source_chart(
            "ewb",
            CommitLocator(commit=SHA),
            cache,
            api,
        )
    assert clock[0] == 3600
    assert calls[0] == 2


def test_oci_auth_failure_never_dispatches(
    services: tuple[FakeCache, FakeAPI, list[tuple[object, ...]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, api, _ = services

    def denied(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("OCI auth")

    monkeypatch.setattr(build_module, "probe_oci_chart", denied)
    with pytest.raises(RuntimeError, match="OCI auth"):
        ensure_source_chart(
            "ewb",
            CommitLocator(commit=SHA),
            cache,
            api,
        )
    assert api.dispatched == []


def test_poll_network_error_stops_after_dispatch(
    services: tuple[FakeCache, FakeAPI, list[tuple[object, ...]]],
    clock: list[float],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cache, api, _ = services
    calls = [False]

    def probe(*args: object, **kwargs: object) -> bool:
        if calls:
            return calls.pop()
        raise RuntimeError("OCI network failure")

    monkeypatch.setattr(build_module, "probe_oci_chart", probe)
    with pytest.raises(RuntimeError, match="OCI network failure"):
        ensure_source_chart(
            "ewb",
            CommitLocator(commit=SHA),
            cache,
            api,
        )
    assert len(api.dispatched) == 1
    assert clock[0] == 0


def test_fork_pr_stops_before_cache_access(
    services: tuple[FakeCache, FakeAPI, list[tuple[object, ...]]],
) -> None:
    cache, api, events = services
    api.pr_error = ValueError("fork rejected")
    with pytest.raises(ValueError, match="fork rejected"):
        ensure_source_chart(
            "ewb",
            PullRequestLocator(pullRequest=42),
            cache,
            api,
        )
    assert events == [("pr_head", REPOSITORIES["ewb"], 42)]


def test_pr_api_rejects_fork_and_uses_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "secret")
    requests_seen: list[tuple[object, ...]] = []

    def request(method: str, url: str, **kwargs: object) -> SimpleNamespace:
        requests_seen.append((method, url, kwargs))
        return SimpleNamespace(
            ok=True,
            json=lambda: {"head": {"sha": SHA, "repo": {"full_name": "outsider/repo"}}},
        )

    monkeypatch.setattr(requests, "request", request)
    with pytest.raises(ValueError, match="comes from a fork"):
        github_api.GitHubAPI().pr_head("energy-workbench-server", 42)
    assert requests_seen[0][2]["headers"]["Authorization"] == "Bearer secret"  # type: ignore[index]


def test_dispatch_payload_uses_default_branch_and_sha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GH_TOKEN", "secret")
    sent: list[tuple[object, ...]] = []

    def request(method: str, url: str, **kwargs: object) -> SimpleNamespace:
        sent.append((method, url, kwargs))
        return SimpleNamespace(ok=True)

    monkeypatch.setattr(requests, "request", request)
    github_api.GitHubAPI().dispatch_build("energy-workbench-server", "main", SHA)
    assert sent[0][0] == "POST"
    assert sent[0][2]["json"] == {"ref": "main", "inputs": {"commit": SHA}}  # type: ignore[index]


@pytest.mark.parametrize("kind", ["auth", "network"])
def test_github_failure_reports_kind_without_token(
    monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    monkeypatch.setenv("GH_TOKEN", "secret")

    def request(method: str, url: str, **kwargs: object) -> SimpleNamespace:
        if kind == "network":
            raise requests.Timeout("private details")
        return SimpleNamespace(ok=False, status_code=403)

    monkeypatch.setattr(requests, "request", request)
    with pytest.raises(RuntimeError, match=f"GitHub API {kind}") as error:
        github_api.GitHubAPI().dispatch_build("energy-workbench-server", "main", SHA)
    assert "secret" not in str(error.value)
    assert "private details" not in str(error.value)
