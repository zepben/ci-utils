"""Git cache behavior against a local remote, without GitHub access."""

import subprocess
from pathlib import Path

import pytest

from zep_dev import git_cache
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
        git_cache.GitCache, "_remote", staticmethod(lambda _name: str(remote))
    )
    return remote, work


def advance(work: Path, content: str) -> str:
    (work / "file").write_text(content, encoding="utf-8")
    git("-C", str(work), "commit", "-am", content)
    git("-C", str(work), "push", "origin", "main")
    return git("-C", str(work), "rev-parse", "HEAD")


def origin_main(repo: Path) -> str:
    return git_cache.GitCache()._commit(repo, "refs/remotes/origin/main")


def test_cache_refreshes_and_calculates_at_frozen_sha(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    first = git_cache.GitCache().ensure_repo("ewb")
    sha = origin_main(first)
    assert sha == git("-C", str(work), "rev-parse", "HEAD")
    assert calculate_chart_version(first, sha) == "1.2.3"

    advanced = advance(work, "two")
    second = git_cache.GitCache().ensure_repo("ewb")
    assert first == second
    assert origin_main(second) == advanced
    assert calculate_chart_version(second, advanced) == f"0.0.0-1.2.3.1+{advanced[:7]}"


def test_cache_fetches_snapshot_tag_and_rejects_untrusted_commit(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    sha = advance(work, "two")
    git("-C", str(work), "tag", "snapshot/v1.3.0b2")
    git("-C", str(work), "push", "origin", "--tags")
    repo = git_cache.GitCache().ensure_repo("ewb")
    assert calculate_chart_version(repo, sha) == "1.3.0-b.2"
    assert git_cache.GitCache().trusted_commit(repo, sha) == sha

    git("-C", str(work), "checkout", "--orphan", "fork-only")
    (work / "file").write_text("fork", encoding="utf-8")
    git("-C", str(work), "add", "file")
    git("-C", str(work), "commit", "-m", "fork")
    untrusted = git("-C", str(work), "rev-parse", "HEAD")
    git("-C", str(work), "push", "origin", "HEAD:refs/pull/42/head")
    with pytest.raises(ValueError, match="not reachable"):
        git_cache.GitCache().trusted_commit(repo, untrusted)


def test_pr_head_movement_fails_without_re_resolution(
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


def test_invalid_cache_is_not_replaced(repository: tuple[Path, Path]) -> None:
    _remote, _work = repository
    path = git_cache.GitCache().root / "energy-workbench-server"
    path.mkdir(parents=True)
    with pytest.raises(ValueError, match="Invalid Git cache"):
        git_cache.GitCache().ensure_repo("ewb")
    assert path.exists()


def test_cache_symlink_is_not_followed(
    repository: tuple[Path, Path], tmp_path: Path
) -> None:
    _remote, work = repository
    path = git_cache.GitCache().root / "energy-workbench-server"
    path.parent.mkdir(parents=True)
    path.symlink_to(work, target_is_directory=True)
    with pytest.raises(ValueError, match="is a symlink"):
        git_cache.GitCache().ensure_repo("ewb")
    assert path.is_symlink()


def test_git_error_names_failed_operation(repository: tuple[Path, Path]) -> None:
    cache = git_cache.GitCache()
    repo = cache.ensure_repo("ewb")
    with pytest.raises(RuntimeError, match="git fetch failed"):
        cache.pr_head_commit(repo, 999999, "0" * 40)
