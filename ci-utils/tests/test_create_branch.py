import os
import pytest

from pathlib import Path

from ci_utils.commands.cmd_create_branch import cli
from click.testing import CliRunner
from test_utils.repo import create_repos_with_tags_branches

from git import Repo

# Create a couple of repos without any specific branches
runner = CliRunner()

@pytest.fixture
def local_path():
    yield Path().absolute()

@pytest.fixture
def local_repo_name(name: str = "local") -> str:
    yield name


@pytest.fixture
def repo_path(local_repo_name: str, local_path):
    yield create_repos_with_tags_branches(local_repo_name)
    os.chdir(local_path)


def test_create_branch_lts_hotfix_no_version(repo_path):
    print(f"Chdir into {repo_path}")
    os.chdir(repo_path)
    result = runner.invoke(cli, ["--type", "lts"])
    assert "Error: version cannot be empty for lts/hotfix branch" in result.output
    assert result.exit_code == 1

    result = runner.invoke(cli, ["--type", "hotfix"])
    assert "Error: version cannot be empty for lts/hotfix branch" in result.output
    assert result.exit_code == 1


def test_create_branch_lts(repo_path):
    print("Testing 'ci creat_branch --type lts --version 0.9'")
    os.chdir(repo_path)

    # Test creating a new branch
    result = runner.invoke(cli, ["--type", "lts", "--version", "0.9"])
    assert result.exit_code == 0
    repo = Repo(repo_path)
    assert "LTS/0.9.X" in (ref.name for ref in repo.heads)


def test_create_branch_lts_bad_tag(repo_path):
    os.chdir(repo_path)

    # Test that creating existing branch fails
    result = runner.invoke(cli, ["--type", "lts", "--version", "0.8"])
    assert "There is already an LTS branch named LTS/0.8.X" in result.output
    assert result.exit_code == 1

    result = runner.invoke(cli, ["--type", "lts", "--version", "0.10"])
    assert "Couldn't find the tag for the version 0.10" in result.output
    assert result.exit_code == 1
#
#
def test_create_branch_hotfix(repo_path):
    os.chdir(repo_path)
    result = runner.invoke(cli, ["--type", "hotfix", "--version", "0.9"])
    assert result.exit_code == 0
    repo = Repo(repo_path)
    assert "hotfix/0.9.3" in (ref.name for ref in repo.heads)


def test_create_branch_hotfix_bad_tag(repo_path):
    os.chdir(repo_path)

    # Test that creating existing branch fails
    result = runner.invoke(cli, ["--type", "hotfix", "--version", "0.8"])
    assert "There is already a hotfix branch named hotfix/0.8.3" in result.output
    assert result.exit_code == 1

    result = runner.invoke(cli, ["--type", "hotfix", "--version", "0.10"])
    assert "Couldn't find the tag for the version 0.10" in result.output
    assert result.exit_code == 1


def test_create_branch_release(repo_path):
    os.chdir(repo_path)
    # Make sure the release branch is not there
    result = runner.invoke(cli, ["--type", "release"])
    repo = Repo(repo_path)
    assert "release" in (ref.name for ref in repo.heads)
    assert result.exit_code == 0

def test_create_release_when_exists(local_path):
    # test that if 'release' already exists, it properly fails
    repo_path = create_repos_with_tags_branches("local", ["release"])
    os.chdir(repo_path)
    # Make sure the release branch is not there
    result = runner.invoke(cli, ["--type", "release"])
    assert "There is already a branch named 'release'" in result.output
    assert result.exit_code == 1
    os.chdir(local_path)
