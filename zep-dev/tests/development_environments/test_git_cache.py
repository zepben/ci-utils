from pathlib import Path

import pytest

from tests.support.git import git
from zep_dev.chart_version import calculate_chart_version
from zep_dev.development_environments import chart_sources as git_cache
from zep_dev.development_environments.chart_sources import VersionChartRef
from zep_dev.errors import ZepDevError
from zep_dev.models import ChartMetadata


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    work = tmp_path / "work"
    git("init", "--bare", "--initial-branch=main", str(remote))
    git("clone", str(remote), str(work))
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
    assert calculate_chart_version(second, sha) == "1.2.3"
    assert calculate_chart_version(second, advanced) == f"0.0.0-1.2.3.1+{advanced[:7]}"


def test_pr_head_movement_is_rejected(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    old = git("-C", str(work), "rev-parse", "HEAD")
    new = advance(work, "two")
    git("-C", str(work), "push", "origin", "HEAD:refs/pull/42/head")
    repo = git_cache.GitCache().ensure_repo("ewb")
    with pytest.raises(ZepDevError, match="moved"):
        git_cache.GitCache().pr_head_commit(repo, 42, old)
    assert git_cache.GitCache().pr_head_commit(repo, 42, new) == new


def test_commit_unreachable_from_default_branch_is_rejected(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    repo = git_cache.GitCache().ensure_repo("ewb")

    git("-C", str(work), "checkout", "--orphan", "fork-only")
    (work / "file").write_text("fork", encoding="utf-8")
    git("-C", str(work), "add", "file")
    git("-C", str(work), "commit", "-m", "fork")
    untrusted = git("-C", str(work), "rev-parse", "HEAD")
    git("-C", str(work), "push", "origin", "HEAD:refs/pull/99/head")
    with pytest.raises(ZepDevError, match="not reachable"):
        git_cache.GitCache().trusted_commit(repo, untrusted)


def test_branch_tracks_remote_head_and_rejects_deleted_branch(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    branch = "feature/integration"
    git("-C", str(work), "push", "origin", f"HEAD:refs/heads/{branch}")
    cache = git_cache.GitCache()
    repo = cache.ensure_repo("ewb")
    assert cache.branch_commit(repo, branch) == git(
        "-C", str(work), "rev-parse", "HEAD"
    )

    new = advance(work, "two")
    git("-C", str(work), "push", "origin", f"HEAD:refs/heads/{branch}")
    cache.ensure_repo("ewb")
    assert cache.branch_commit(repo, branch) == new

    git("-C", str(work), "push", "origin", "--delete", branch)
    cache.ensure_repo("ewb")
    with pytest.raises(ZepDevError, match="not found in source repository"):
        cache.branch_commit(repo, branch)


def published_at(commit: str) -> ChartMetadata:
    return ChartMetadata(
        name="eas",
        version="1.2.3",
        annotations={
            "zepben.com/source-commit": commit,
            "zepben.com/runtime-contract-ref": "contract",
        },
    )


def test_published_chart_kind_wrapper_is_fetched_at_its_source_commit(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    wrapper = work / "helm/charts/eas/kind-runtime-contract"
    wrapper.mkdir(parents=True)
    (wrapper / "main.tf").write_text("", encoding="utf-8")
    git("-C", str(work), "add", "helm")
    git("-C", str(work), "commit", "-m", "kind wrapper")
    git("-C", str(work), "push", "origin", "main")
    commit = git("-C", str(work), "rev-parse", "HEAD")
    ref = VersionChartRef(name="eas", version="1.2.3")

    assert git_cache.ChartResolver().kind_wrapper(ref, published_at(commit)) == (
        "git::ssh://git@github.com/zepben/evolve-app-server.git"
        f"//helm/charts/eas/kind-runtime-contract?ref={commit}"
    )


def test_published_chart_without_kind_wrapper_at_its_source_commit_has_none(
    repository: tuple[Path, Path],
) -> None:
    _remote, work = repository
    commit = git("-C", str(work), "rev-parse", "HEAD")
    ref = VersionChartRef(name="eas", version="1.2.3")

    assert git_cache.ChartResolver().kind_wrapper(ref, published_at(commit)) is None


@pytest.mark.parametrize(
    "annotations",
    [{}, {"zepben.com/source-commit": "a" * 40}],
    ids=["no-source-commit", "no-runtime-contract"],
)
def test_published_chart_that_cannot_have_a_kind_wrapper_is_not_fetched(
    annotations: dict[str, str],
) -> None:
    ref = VersionChartRef(name="eas", version="1.2.3")
    published = ChartMetadata(name="eas", version="1.2.3", annotations=annotations)

    assert git_cache.ChartResolver().kind_wrapper(ref, published) is None
    assert not git_cache.GitCache().root.exists()
