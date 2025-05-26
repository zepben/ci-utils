import os
from typing import Generator

import pytest

from pathlib import Path

from ci_utils.commands.cmd_update_version import cli
from ci_utils.utils.version import VersionUtils
from click.testing import CliRunner
from test_utils.repo import create_repos_with_tags_branches
from test_utils.configs import configs, goodbranch

from ci_utils import Environment
from ci_utils.utils.git import Git

# Create a couple of repos without any specific branches
runner = CliRunner()
ctx = Environment()


@pytest.fixture
def local_path() -> Generator[Path, None, None]:
    yield Path().absolute()


@pytest.fixture
def local_repo_name(name: str = "local") -> Generator[str, None, None]:
    yield name


@pytest.fixture
def repo_path(local_repo_name: str, local_path, request):
    yield create_repos_with_tags_branches(name=local_repo_name, include_project_files=True)
    os.chdir(local_path)


def test_update_snapshot_version(repo_path):
    for config in configs.values():
        # Test command: ci update_version --lang ... --project-file  --snapshot
        #   will test all languages and project files
        os.chdir(repo_path)

        # checkout a branch different from main
        git = Git(ctx)
        git.checkout(goodbranch)

        runner.invoke(cli, 
              ["--lang", config.lang, 
               "--project-file", config.project_file, 
               "--snapshot"])

        # now fetch it and check the version was updated
        utils = VersionUtils(ctx, config.lang, config.project_file)
        version, sem_version = utils.lang_utils.parse_project_version(config.project_file)
        assert version == f"{config.next_snapshot}"

        # now check it's been pushed to the origin
        for br in git.repo.remotes.origin.refs:
            if br.name.split("/")[-1] == "good-branch":
                assert git.repo.head.commit.hexsha == br.commit.hexsha

def test_update_version(repo_path):
    for config in configs.values():
        # Test command: ci update_version --lang ... --project-file ... --changelog-file ...
        #   will test all languages and project files
        os.chdir(repo_path)

        # checkout a branch different from main
        git = Git(ctx)
        git.checkout(goodbranch)

        res = runner.invoke(cli, 
              ["--lang", config.lang, 
               "--project-file", config.project_file, 
               "--changelog-file", config.changelog])

        print(res.output)

        # now fetch it and check the version was updated
        utils = VersionUtils(ctx, config.lang, config.project_file)
        version, sem_version = utils.lang_utils.parse_project_version(str(os.path.join(repo_path, config.project_file)))

        # so we've upgraded the whole version, it means it needs to be minor update
        new_version = config.released_tag.split(".")
        assert sem_version == f"{new_version[0]}.{int(new_version[1])+1}.0"

        # now check it's been pushed to the origin
        for br in git.repo.remotes.origin.refs:
            if br.name.split("/")[-1] == "good-branch":
                assert git.repo.head.commit.hexsha == br.commit.hexsha
