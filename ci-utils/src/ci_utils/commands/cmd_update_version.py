import click
import os
import re

from ci_utils import pass_environment
from ci_utils.utils.git import Git
from ci_utils.utils.version import VersionUtils


@click.command("update-version",
               help="Update the project version to the next one (patch version for LTS, minor version for all others).",
               short_help="Update the project version to the next one (patch version for LTS, minor version for all others)."
               )
@click.option("--lang",
              required=True,
              type=click.Choice(["jvm", "csharp", "python", "js"]),
              help="Language that's used for various project file parsing")
@click.option("--project-file",
              required=True,
              type=str,
              help="The project file path, i.e setup.py, pom.xml, etc")
@click.option("--changelog-file",
              required=False,
              type=str,
              show_default=True,
              help="The changelog file path, i.e changelog.md. Cannot be used together with --snapshot")
@click.option("--commit",
              is_flag=True,
              required=False,
              type=bool,
              default=True,
              show_default=True,
              help="Commit updates to the origin")
@click.option("--snapshot",
              is_flag=True,
              required=False,
              type=bool,
              default=False,
              show_default=True,
              help="Increments the snapshot version. Only useful for snapshot builds. Cannot be used together with --changelog-file")
@click.option("--release",
              is_flag=True,
              required=False,
              type=bool,
              default=False,
              show_default=True,
              help="Use this option on create release step")
@click.option("--grow-changelog",
              is_flag=True,
              required=False,
              type=bool,
              default=False,
              show_default=True,
              help="Updates changelog by inserting EDNAR-style template instead of resetting it to the regular one.")
@pass_environment
def cli(ctx, lang, project_file, changelog_file, commit, snapshot, release, grow_changelog):

    ctx.info(f"""Running with following parameters:
        language: {lang}
        project file: {project_file}
        changelog file: {changelog_file}
        commit: {commit}
        snapshot: {snapshot}
        release: {release}
        grow-changelog: {grow_changelog}
    """)

    if snapshot and changelog_file:
        ctx.fail("Snapshot and changelog options were provided at the same time. They cannot be used together.")

    # Do the repo init via the ctx object?
    git = Git(ctx)

    # Fetch just in case
    git.repo.remotes.origin.fetch(refspec="+refs/heads/*:refs/remotes/origin/*")

    branch = os.getenv('GITHUB_REF', git.repo.active_branch.name)
    ctx.info(f"Running on branch: {branch}")

    # if --release option was provided and we're on a hotfix branch, drop the current branch and release branch and ...we're done
    if release and re.match(".*hotfix/.*", branch):
        git.delete_remote_branch(branch)
        # delete release branch if it exists
        git.delete_remote_branch("release")
        os.exit(0)

    if not os.path.exists(project_file):
        ctx.fail(f"The provided {project_file} doesn't seem to exist!")

    # Update project version
    ctx.info("Updating version...")

    # Create version utils
    utils = VersionUtils(ctx, lang=lang, project_file=project_file)

    if snapshot:
        utils.update_snapshot_version()
    else:
        # TODO: consider uniting both ifs
        if commit:
            # if we commit stuff...checkout release branch or current GITHUB_REF.
            co_branch = "release" if release else branch
            git.checkout(co_branch)

        version_type = "patch" if re.match(".*[LTS|hotfix]/.*", branch) else "minor"
        utils.update_version(version_type)

    # Update changelog
    if changelog_file:
        utils.update_changelog(grow_changelog, changelog_file)

    # stage updates
    ctx.info("Stage updates")
    git.stage([project_file, changelog_file])
    # show status for debugging
    ctx.info("Git status:")
    git.status()

    # TODO: Double negative yay
    if commit:
        ctx.info("Commit updates")
        if release:
            git.commit_update_version()
            git.checkout(branch)
            git.pull("release")
            git.push(branch)
            git.delete_remote_branch("release")
        else:
            git.commit_update_version(branch)
