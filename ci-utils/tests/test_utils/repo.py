import shutil
import os

from jinja2 import Environment, FileSystemLoader

from git import Repo, Actor
from test_utils.configs import configs, goodbranch

# Now this needs to hail one folder upwards, as we're in test_utils
environment = Environment(loader=FileSystemLoader(
    os.path.join(os.path.dirname(__file__), "../", "test_files")))

def create_project_file(config, path):
    template = environment.get_template(config.project_file)
    content = template.render(current_version=config.current_version)
    fpath = os.path.join(path, config.project_file)
    with open(fpath, "w") as f:
        print(f"Saving {fpath}")
        f.write(content)
    return fpath


# Utility function to create a local repo. Returns the repo path
def create_repos_with_tags_branches(
        name: str,
        branches: list[str] = [],
        tags: list[str] = [],
        include_project_files: bool = False) -> str:
    print(
        f"Setting up 2 repos: in /tmp/remote and /tmp/{name}\nwith branches: {branches} and tags: {tags}"
    )
    print(f"Current path: {os.path.realpath('.')}")

    # Create a "remote"
    remote = "remote"
    remote_path = os.path.join("/tmp", remote)
    if os.path.exists(remote_path):
        shutil.rmtree(remote_path)

    # Create a local path
    local_path = os.path.join("/tmp", name)
    if os.path.exists(local_path):
        shutil.rmtree(local_path)

    # init remote repo with main branch
    repo = Repo.init(os.path.join(remote_path), b="main")

    # add a couple of files
    for fname in ("f1.txt", "f2.txt"):
        with open(os.path.join(remote_path, fname), "w") as f:
            f.write(f"This is a test files with name {f.name}")
        repo.index.add(f.name)

    # add changelogs and project files
    files = []
    if include_project_files:
        for f in ("changelog-python.md", "changelog-js.md", "changelog-jvm.md",
                  "changelog-cs.md"):
            shutil.copy(os.path.join("tests", "test_files", f),
                        os.path.join(remote_path, f))
            files.append(f)

        for config in configs.values():
            create_project_file(config, remote_path)
            files.append(config.project_file)

    repo.index.add(files)
    # commit
    repo.index.commit("Init", author=Actor("CI", "ci@zepben.com"))

    # create test branches
    if len(branches) == 0:
        branches = ("test-branch", "LTS/0.8.X", "hotfix/0.8.3")
    for br in branches:
        print(f"Creating branch {br}")
        repo.create_head(br)

    if len(tags) == 0:
        tags = [config.released_tag for config in configs.values()]
        tags.extend(("tag1", "tag2", "v0.8.1", "v0.8.2", "v0.9.1",
                         "v0.9.2"))
    for tag in tags:
        repo.create_tag(tag)

    # Now clone to "local" repo
    local_path = os.path.join("/tmp", name)
    Repo.clone_from(remote_path, local_path)

    local = Repo(local_path)
    local.remotes.origin.fetch()

    # Create a new branch in the local repo with new commit
    head_ref = local.head.ref
    ref = local.create_head(goodbranch, "main")
    local.head.ref = ref

    with open(os.path.join(local_path, "f3.txt"), "w") as f:
        print(f"Writing out {f.name}")
        f.write(f"This is a test files with name {f.name}")
    local.index.add("f3.txt")

    # commit
    local.index.commit("New stuff", author=Actor("CI", "ci@zepben.com"))

    # Switch back to main
    local.head.ref = head_ref

    # Return local path
    return local_path
