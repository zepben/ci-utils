import os
import pytest

from typing import Generator

from ci_utils import Environment
from ci_utils.utils.git import Git
from test_utils.repo import create_repos_with_tags_branches
from test_utils.configs import goodbranch

from pathlib import Path



ctx = Environment()
branch = "test-branch"


@pytest.fixture
def local_repo_name(name: str = "local") -> Generator[str, None, None]:
    yield name


@pytest.fixture
def git(local_repo_name: str):
    local_path = Path().absolute()
    repo_path = create_repos_with_tags_branches(name=local_repo_name, branches=[branch])
    yield Git(ctx, repo_path)
    os.chdir(local_path)


# Delete branch from remote and check it's gone
def test_delete_remote_branch(git):
    git.delete_remote_branch(branch)
    git.repo.remotes.origin.fetch()
    assert branch not in git.repo.remotes.origin.refs


# This checks the existence of a tag in a remote repo
# Negative test
#    check that some random tag doesn't exist (UUID?)
# Positive test.
#    check that tag1 and tag2 are present
# Check it exists
def test_tag_exists(git):
    assert git.tag_exists("aklsdfjlasjdlkfjalsdflk") is False
    assert git.tag_exists("tag1") is True
    assert git.tag_exists("tag2") is True


def test_checkout(git):
    git.checkout(goodbranch)
    assert git.repo.active_branch.name == goodbranch
