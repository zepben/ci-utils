import os
import pytest

from pathlib import Path
from test_utils.repo import create_repos_with_tags_branches


@pytest.fixture
def local_path():
    yield Path().absolute()


@pytest.fixture
def local_repo_name(name: str = "local") -> str:
    yield name


@pytest.fixture
def repo_path(local_repo_name: str, local_path, request):
    yield create_repos_with_tags_branches(name=local_repo_name,
                                          include_project_files=True)
    os.chdir(local_path)

@pytest.mark.skip()
def test_finalise():
    assert 1 == 0
