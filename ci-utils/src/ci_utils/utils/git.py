import os
import re

import subprocess

from git import Repo, Actor


class Git:
    def __init__(self, ctx, path: str = ""):
        self.ctx = ctx
        self.remote_refs = {"heads": [], "tags": []}
        self.path = path
        self.init_git()

    def init_git(self):
        if self.path != "":
            os.chdir(self.path)
        path = subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).strip().decode("utf-8")
        self.repo = Repo(path)
        self.ls_remotes()

    # TODO: consider renaming to fetch_remotes() and just use the object field
    # Also, obviously, test if we even need to use ls_remotes or local tags are ok
    def ls_remotes(self):
        if len(self.remote_refs["heads"]) > 0:
            return self.remote_refs

        def parse_refs(ref: str):
            found_ref = re.search(".*(?P<ref_type>heads|tags).*", ref)
            if found_ref:
                ref_type = found_ref.group("ref_type")
                # only keep the actual tag or reference (branch) name
                return (ref_type, found_ref.group(0).replace(f"refs/{ref_type}/",''))

        # Now filter out heads/tags
        for pair in list(map(parse_refs, (ref.split("\t")[1] for ref in self.repo.git.ls_remote().split("\n")))):
            if pair is not None:
                self.remote_refs[pair[0]].append(pair[1])

    def delete_remote_branch(self, branch: str):
        if branch in (b.split('/')[-1] for b in self.remote_refs['heads']):
            self.repo.remotes.origin.push(refspec=(f":{branch}"))

    def tag_exists(self, version: str) -> bool:
        self.ctx.info(f"Checking remote tags if version {version} exists...")
        for tag in self.remote_refs["tags"]:
            if re.match(f"(^v)*{version}$", tag):
                self.ctx.warn(f"Tag for this version {version} already exists")
                return True

        return False

    # TODO: check what happens if we just create_head without the second param
    #  if that works, then we only need to track the remote branch, everything
    #  else should be the same
    def checkout(self, branch: str):
        found_branch = False

        # Check if local exists and checkout if so
        for b in self.repo.heads:
            if branch == b.name:
                b.checkout()
                found_branch = True
                break

        # if not found the local, check remotes
        if not found_branch:
            for b in self.repo.remotes.origin.refs:
                if branch == b.name.split('/')[-1]:
                    # create a new branch and set tracking to remote
                    ref = self.repo.create_head(branch, b)
                    self.repo.heads[branch].set_tracking_branch(b)
                    ref.checkout()
                    found_branch = True
                    break

        # If still not found, just create a new
        if not found_branch:
            ref = self.repo.create_head(branch)
            ref.checkout()

        self.repo.head.reset(index=True, working_tree=True)

    def stage(self, files: list[str]):
        # Handle the None case
        self.repo.index.add((f for f in files if f))

    def status(self):
        self.ctx.info(self.repo.git.status("-uno"))

    def commit(self, comment: str = ""):
        if len(comment) == 0:
            self.ctx.fail("Cannot commit code without comment!")

        self.repo.index.commit(comment, author=Actor("CI", "ci@zepben.com"))

    def pull(self, branch):
        self.repo.remotes.origin.pull(branch)

    def push(self, branch):
        self.repo.remotes.origin.push(refspec=(f"{branch}:{branch}")).raise_if_error()

    def commit_update_version(self, branch: str = ""):
        if len(branch) == 0:
            branch = "release"

        self.ctx.info(f"Commiting changes to {branch}...")
        self.commit(comment="Update version to next snapshot [skip ci]")
        self.push(branch)

    def commit_finalise_version(self, old_version, new_version):
        self.commit(comment=f"Update {old_version} to {new_version} [skip ci]")
        self.push("release")
