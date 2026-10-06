"""Source pin resolution, dispatch, and trust boundaries."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import requests
from click.testing import CliRunner

from zep_dev import chart_artifacts
from zep_dev.chart_artifacts import ChartResolver, GitCache
from zep_dev.cli import cli
from zep_dev.commands.distribution import build as build_module
from zep_dev.distribution import CommitLocator, PullRequestLocator
from zep_dev.github_api import GitHubAPI

SHA = "a" * 40


@dataclass
class FakeCache(GitCache):
    repo: Path
    events: list[tuple[object, ...]] = field(default_factory=list)

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
    dispatched: list[tuple[str, str, str]] = field(default_factory=list)

    def pr_head(self, repo_name: str, number: int) -> str:
        return SHA

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
        chart_artifacts, "calculate_chart_version", lambda repo, sha: "1.2.3"
    )
    return ChartResolver(cache=fake_cache, api=fake_api)


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        (PullRequestLocator(pullRequest=42), ("pr_head_commit", 42, SHA)),
        (CommitLocator(commit=SHA), ("trusted_commit", SHA)),
    ],
)
def test_present_source_chart_preserves_sha_without_dispatch(
    resolver: ChartResolver,
    fake_cache: FakeCache,
    fake_api: FakeAPI,
    monkeypatch: pytest.MonkeyPatch,
    locator: PullRequestLocator | CommitLocator,
    expected: tuple[object, ...],
) -> None:
    monkeypatch.setattr(chart_artifacts, "probe_oci_chart", lambda *args, **kw: True)

    ref = resolver.resolve("ewb", locator)
    resolver.ensure(ref)

    assert ref.sha == SHA
    assert (expected[0], fake_cache.repo, *expected[1:]) in fake_cache.events
    assert fake_api.dispatched == []


def test_cli_build_source_pin_when_oci_present(
    write_distribution: Callable[..., Path],
    resolver: ChartResolver,
    fake_cache: FakeCache,
    fake_api: FakeAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = write_distribution(ewb={"pullRequest": 42})
    monkeypatch.setattr(build_module, "ChartResolver", lambda: resolver)
    monkeypatch.setattr(chart_artifacts, "probe_oci_chart", lambda *args, **kw: True)

    result = CliRunner().invoke(
        cli, ["distribution", "build", "--distribution", str(path)]
    )

    assert result.exit_code == 0, result.exception or result.output
    assert ("pr_head_commit", fake_cache.repo, 42, SHA) in fake_cache.events
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

    with pytest.raises(ValueError, match="comes from a fork"):
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
    monkeypatch.setattr(chart_artifacts, "probe_oci_chart", lambda *args, **kw: False)
    ref = resolver.resolve("ewb", CommitLocator(commit=SHA))

    with pytest.raises(FileNotFoundError, match="GHCR credentials missing"):
        resolver.ensure(ref)

    assert fake_api.dispatched == []


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


def test_missing_source_chart_dispatches_and_waits_for_oci(
    tmp_path: Path,
    resolver: ChartResolver,
    fake_api: FakeAPI,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    registry = tmp_path / "registry.json"
    registry.write_text('{"auths": {"ghcr.io": {}}}\n', encoding="utf-8")
    monkeypatch.setenv("HELM_REGISTRY_CONFIG", str(registry))
    monkeypatch.setattr(chart_artifacts, "_POLL_INTERVAL", 0)
    reports: list[bool] = []

    def probe(
        name: str,
        version: str,
        *,
        report: bool = True,
        timeout: float = chart_artifacts.OCI_PROBE_TIMEOUT,
    ) -> bool:
        assert (name, version) == ("ewb", "1.2.3")
        reports.append(report)
        return len(reports) == 3

    monkeypatch.setattr(chart_artifacts, "probe_oci_chart", probe)
    ref = resolver.resolve("ewb", CommitLocator(commit=SHA))
    resolver.ensure(ref)

    assert fake_api.dispatched == [("energy-workbench-server", "main", SHA)]
    assert reports == [True, False, False]
    assert capsys.readouterr().out.splitlines()[-1] == "  ready ewb:1.2.3"
