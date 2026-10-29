"""Source selection resolution, build dispatch, and trust boundaries."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import override

import pytest
import requests

from tests.support.clock import FakeClock
from zep_dev.development_environments import chart_sources
from zep_dev.development_environments.chart_sources import ChartResolver, GitCache
from zep_dev.development_environments.distributions import (
    BranchLocator,
    CommitLocator,
    PullRequestLocator,
)
from zep_dev.errors import ZepDevError
from zep_dev.github_api import GitHubAPI
from zep_dev.models import ChartMetadata

SHA = "a" * 40


@dataclass
class FakeCache(GitCache):
    repo: Path
    events: list[tuple[object, ...]] = field(default_factory=list)

    @override
    def ensure_repo(self, name: str) -> Path:
        self.events.append(("ensure_repo", name))
        return self.repo

    @override
    def pr_head_commit(self, repo: Path, number: int, expected: str) -> str:
        self.events.append(("pr_head_commit", repo, number, expected))
        return SHA

    @override
    def branch_commit(self, repo: Path, branch: str) -> str:
        self.events.append(("branch_commit", repo, branch))
        return SHA

    @override
    def trusted_commit(self, repo: Path, sha: str) -> str:
        self.events.append(("trusted_commit", repo, sha))
        return sha

    @override
    def default_branch(self, repo: Path) -> str:
        self.events.append(("default_branch", repo))
        return "main"


@dataclass
class FakeAPI(GitHubAPI):
    dispatched: list[tuple[str, str, str]] = field(default_factory=list)

    @override
    def pr_head(self, repo_name: str, number: int) -> str:
        return SHA

    @override
    def dispatch_build(self, repo_name: str, branch: str, sha: str) -> None:
        self.dispatched.append((repo_name, branch, sha))


@pytest.fixture
def fake_cache(tmp_path: Path) -> FakeCache:
    return FakeCache(tmp_path / "cache")


@pytest.fixture
def fake_api() -> FakeAPI:
    return FakeAPI()


@pytest.fixture
def resolver(
    fake_cache: FakeCache, fake_api: FakeAPI, monkeypatch: pytest.MonkeyPatch
) -> ChartResolver:
    monkeypatch.setattr(
        chart_sources, "calculate_chart_version", lambda repo, sha: "1.2.3"
    )
    return ChartResolver(cache=fake_cache, api=fake_api, progress=print)


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        (PullRequestLocator(pullRequest=42), ("pr_head_commit", 42, SHA)),
        (
            BranchLocator(branch="feature/integration"),
            ("branch_commit", "feature/integration"),
        ),
        (CommitLocator(commit=SHA), ("trusted_commit", SHA)),
    ],
)
def test_present_source_chart_preserves_sha_without_dispatch(
    resolver: ChartResolver,
    fake_cache: FakeCache,
    fake_api: FakeAPI,
    monkeypatch: pytest.MonkeyPatch,
    locator: PullRequestLocator | BranchLocator | CommitLocator,
    expected: tuple[object, ...],
) -> None:
    published = ChartMetadata(name="ewb", version="1.2.3")
    monkeypatch.setattr(chart_sources, "probe_oci_chart", lambda *args, **kw: published)

    ref = resolver.resolve("ewb", locator)
    resolver.ensure(ref)

    assert isinstance(ref, chart_sources.SourceChartRef)
    assert ref.sha == SHA
    assert (expected[0], fake_cache.repo, *expected[1:]) in fake_cache.events
    assert fake_api.dispatched == []


def test_fork_pr_stops_before_cache_access(
    fake_cache: FakeCache, monkeypatch: pytest.MonkeyPatch
) -> None:
    response = requests.Response()
    response.status_code = 200
    response._content = json.dumps(
        {
            "head": {
                "sha": SHA,
                "repo": {"full_name": "outsider/energy-workbench-server"},
            }
        }
    ).encode()
    monkeypatch.setenv("GH_TOKEN", "test-token")
    monkeypatch.setattr(requests, "request", lambda *args, **kwargs: response)
    resolver = ChartResolver(cache=fake_cache, api=GitHubAPI())

    with pytest.raises(ZepDevError, match="comes from a fork"):
        resolver.resolve("ewb", PullRequestLocator(pullRequest=42))

    assert fake_cache.events == []


def test_missing_ghcr_entry_fails_before_dispatch(
    tmp_path: Path,
    resolver: ChartResolver,
    fake_api: FakeAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text('{"auths": {}}\n', encoding="utf-8")
    monkeypatch.setenv("HELM_REGISTRY_CONFIG", str(registry))
    monkeypatch.setattr(chart_sources, "probe_oci_chart", lambda *args, **kw: None)
    ref = resolver.resolve("ewb", CommitLocator(commit=SHA))

    with pytest.raises(ZepDevError, match="GHCR credentials missing"):
        resolver.ensure(ref)

    assert fake_api.dispatched == []


def test_missing_source_chart_dispatches_and_waits_for_oci(
    fake_clock: FakeClock,
    tmp_path: Path,
    resolver: ChartResolver,
    fake_api: FakeAPI,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text('{"auths": {"ghcr.io": {}}}\n', encoding="utf-8")
    monkeypatch.setenv("HELM_REGISTRY_CONFIG", str(registry))
    probes: list[tuple[str, str]] = []

    def published(name: str, version: str) -> ChartMetadata | None:
        probes.append((name, version))
        return ChartMetadata(name=name, version=version) if len(probes) == 3 else None

    monkeypatch.setattr(chart_sources, "published_chart_metadata", published)
    ref = resolver.resolve("ewb", CommitLocator(commit=SHA))
    resolver.ensure(ref)

    assert reports == [True, False, False]
    assert fake_api.dispatched == [("energy-workbench-server", "main", SHA)]
    assert capsys.readouterr().out.splitlines()[-1] == "  ready ewb:1.2.3"
