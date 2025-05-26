import click
import datetime

from ci_utils import pass_environment
from ci_utils.utils.git import Git
from ci_utils.utils.version import VersionUtils

# finalise-version --lang (csharp, js, kotlin, python) [--no-commit] --project-file <package.json, pom.xml, setup.py> --changelog <changelog.md>


@click.command(
    "finalise_version",
    help="""Finalise release version by removing SNAPSHOT, next, etc.;
            tag and push the commit to a branch named `release`;
            add a new entry to the changelog when command is specified.
    """,
    short_help="Finalise, tag and push release version (and update changelog)",
)
@click.option(
    "--lang",
    required=True,
    type=click.Choice(["jvm", "csharp", "python", "js"]),
    help="Language that's used for various project file parsing",
)
@click.option("--project-file",
              required=True,
              type=str,
              help="The project file path, i.e setup.py, pom.xml, etc")
@click.option(
    "--changelog-file",
    required=False,
    type=str,
    default="changelog.md",
    show_default=True,
    help="The changelog file path, i.e changelog.md",
)
@click.option("--commit",
              is_flag=True,
              required=False,
              type=bool,
              default=True,
              show_default=True,
              help="Commit updates")
@pass_environment
def cli(ctx, lang, project_file, changelog_file, commit):
    ctx.info(f"""Running with following parameters:
        language: {lang}
        project file: {project_file}
        changelog file: {changelog_file}
        commit: {commit}
    """)

    ctx.info("Finalizing version...")
    git = Git(ctx)

    if commit:
        git.checkout("release")

    version_utils = VersionUtils(ctx, lang, project_file)

    if changelog_file:
        ctx.info("Timestamping version in changelog...")
        new_changelog: list[str] = []
        with open(changelog_file, "r") as f:
            text = f.read()
            new_changelog = text.replace("UNRELEASED", datetime.datetime.now().strftime("%Y-%m-%d"))

        if len(new_changelog) > 0:
            with open(changelog_file, "w") as f:
                f.write("\n".join(new_changelog))

    # stage updates
    git.stage([project_file, changelog_file])
    # show status for debugging
    git.status()

    if commit:
        if not git.tag_exists(version_utils.new_version):
            git.commit_finalise_version(version_utils.sem_version, version_utils.new_version)
