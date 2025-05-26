import os
import pytest

from pathlib import Path
from git import Repo

from ci_utils.commands.cmd_release_checks import cli
from click.testing import CliRunner
from test_utils.repo import create_repos_with_tags_branches
from test_utils.configs import configs

runner = CliRunner()


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


def test_release_checks_existing_release(repo_path):
    # Test command: ci release_checks --lang ... --project-file ...
    # The current branch (sha) already exists in the remote for other tags, should error out
    os.chdir(repo_path)
    for config in configs.values():
        result = runner.invoke(cli, [
            "--lang", config.lang, "--project-file",
            os.path.join(repo_path, config.project_file)
        ])
        assert "Can't run release pipeline. This commit" in result.output
        assert result.exit_code == 1


def test_release_checks_new_release(repo_path):
    # Test command: ci release_checks --lang ... --project-file ...
    # the current sha doesn't exist in remote at all, so should succeed
    os.chdir(repo_path)
    repo = Repo(repo_path)
    for br in repo.heads:
        if br.name == "not_released":
            # Checkout the "not_released" branch, should return success
            repo.head.ref = br
            for config in configs.values():
                result = runner.invoke(cli, [
                    "--lang", config.lang, "--project-file",
                    config.project_file
                ])
                assert result.exit_code == 0
