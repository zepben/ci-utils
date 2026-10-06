import subprocess
from pathlib import Path

import pytest

from zep_dev import chart_artifacts as git_cache
from zep_dev.commands.chart.version import calculate_chart_version


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], text=True, capture_output=True, check=True
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git("init", "--bare", "--initial-branch=main", str(remote))
    git("clone", str(remote), str(work))
    git("-C", str(work), "config", "user.email", "test@example.com")
    git("-C", str(work), "config", "user.name", "Test")
    (work / "file").write_text("one", encoding="utf-8")
    git("-C", str(work), "add", "file")
    git("-C", str(work), "commit", "-m", "initial")
    git("-C", str(work), "tag", "v1.2.3")
    git("-C", str(work), "push", "origin", "main", "--tags")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setattr(
        git_cache.GitCache, "remote", staticmethod(lambda _name: str(remote))
    )
    return remote, work


def advance(work: Path, content: str) -> str:
    (work / "file").write_text(content, encoding="utf-8")
    git("-C", str(work), "commit", "-am", content)
    git("-C", str(work), "push", "origin", "main")
    return git("-C", str(work), "rev-parse", "HEAD")


def test_cache_refreshes_and_calculates_at_frozen_sha(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    first = git_cache.GitCache().ensure_repo("ewb")
    sha = git_cache.GitCache().commit(first, "refs/remotes/origin/main")
    assert calculate_chart_version(first, sha) == "1.2.3"
    advanced = advance(work, "two")
    second = git_cache.GitCache().ensure_repo("ewb")
    assert first == second
    assert calculate_chart_version(second, advanced) == f"0.0.0-1.2.3.1+{advanced[:7]}"


def test_pr_head_movement_and_untrusted_commit(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    old = git("-C", str(work), "rev-parse", "HEAD")
    new = advance(work, "two")
    git("-C", str(work), "push", "origin", "HEAD:refs/pull/42/head")
    repo = git_cache.GitCache().ensure_repo("ewb")
    with pytest.raises(RuntimeError, match="moved"):
        git_cache.GitCache().pr_head_commit(repo, 42, old)
    assert git_cache.GitCache().pr_head_commit(repo, 42, new) == new

    git("-C", str(work), "checkout", "--orphan", "fork-only")
    (work / "file").write_text("fork", encoding="utf-8")
    git("-C", str(work), "add", "file")
    git("-C", str(work), "commit", "-m", "fork")
    untrusted = git("-C", str(work), "rev-parse", "HEAD")
    git("-C", str(work), "push", "origin", "HEAD:refs/pull/99/head")
    with pytest.raises(ValueError, match="not reachable"):
        git_cache.GitCache().trusted_commit(repo, untrusted)
