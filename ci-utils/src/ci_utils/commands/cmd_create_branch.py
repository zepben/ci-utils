import click
import re
import os

from ci_utils import pass_environment
from ci_utils.utils.git import Git
from ci_utils.utils.version import VersionUtils
from ci_utils.utils.slack import Slack


@click.command(name="create-branch",
               help="""Creates a branch from a list of (lts, hotfix, release). 
               The version provided (git tag) should match the type of the branch:\n
                   * For LTS, it should match the preexisting tag, i.e. for a new LTS in 0.9 line, the version should be 0.9, this will create a branch LTS/0.9.X\n
                   * For Hotfix, it should match the preexisting tag, i.e. for a new hotfix in 0.9 line, the version should be 0.9, this will create a branch hotfix/0.9.X\n
                   * Release branch creation doesn't require version and will ignore it if provided. It will spawn the "release" branch from the currently checked out branch.\n
               """,
               short_help="Creates a branch from a list of (lts, hotfix, release)")
@click.option("--type", "btype", required=True, type=click.Choice(["lts", "hotfix", "release"]))
@click.option("--version", required=False, type=str)
@pass_environment
def cli(ctx, btype, version):
    """Creates a branch from a list of (lts, hotfix, release)"""

    if btype != "release" and version is None:
        ctx.fail("Error: version cannot be empty for lts/hotfix branch")
    else:
        ctx.info(f"Creating branch of type {btype} for version {version}")

    git = Git(ctx)

    # Definitions
    tag: str = None
    version_array: list[str] = None
    commit: str = None
    branch: str = None

    # tag list matching the provided version
    if btype == "release":
        commit = "main"
    elif version is not None:
        tags = [t.name for t in git.repo.tags
                if re.match(rf"v*{version}\.[0-9]+", t.name)]

        # if found tags, pick the last one
        if len(tags) > 0:
            tag = tags[-1]
            ctx.info(f"Found {tag}")
        else:
            ctx.fail(f"Couldn't find the tag for the version {version}")
            return

        version = tag.replace('v', '')
        commit = git.repo.rev_parse(tag)

        # Check that version has the correct pattern
        version_utils = VersionUtils(ctx)
        version_utils.validate_version(version)
        version_array = version.split('.')

        ctx.info(f"commit={commit}")

    match btype:
        case "lts":
            branch = f"LTS/{version_array[0]}.{version_array[1]}.X"
            if branch in git.remote_refs["heads"]:
                ctx.fail(
                    f"There is already an LTS branch named {branch}.")

        case "hotfix":
            # figure out the next version
            next_version = f"{version_array[0]}.{version_array[1]}.{int(version_array[2]) + 1}"
            if f"v{next_version}" in git.remote_refs["tags"]:
                ctx.fail(
                    f"{version} is not the latest tag for {version_array[0]}.{version_array[1]}.")

            branch = f"hotfix/{next_version}"
            if branch in git.remote_refs["heads"]:
                ctx.fail(f"There is already a hotfix branch named {branch}.")

        case "release":
            if "release" in git.remote_refs["heads"]:
                ctx.fail("There is already a branch named 'release'.")

            branch = "release"

    # info "Creating the branch and checkout"

    ctx.info(f"Checking out {branch} off {commit}")
    try:
        ref = git.repo.create_head(branch, commit)
        ref.checkout()
        actor = os.getenv('GITHUB_ACTOR')
        Slack(ctx).send_message(f"Created branch *{branch}* (by *{actor}*)")
        ctx.info(f"Branch {branch} created and checked out successfully")
    except Exception as err:
        ctx.fail(f"Failed to checkout branch {branch}: {err}")
