# CI utils package for Zepben CI 

This is a ci-utils package that include all the utility commands for Zepben CI and related container packaging.

The package includes:

/container - the definitions to build the base container for building all Zepben projects. This should support:
    * python
    * java/kotlin
    * js
    * csharp

/src - the python package for ci utilities. These are used to work on branches, update versions, update changelogs, etc.

## Commands List

### Release Checks

Used to make sure commit has not been released, last build was successful and notify team via Slack that release pipeline has been triggered.


> ci release-checks --lang (csharp, js, kotlin, python) --project-file <package.json, pom.xml, setup.py>

### Create Branch
This command is used to create a branch in a working git tree. It's not a generic "create branch" command (at this stage),
and is only used to create a predefined branch - a `hotfix/version` branch, an `lts/version` branch or a `release` branch. 

Create the LTS/hotfix branch
 Options:
   --type lts       - Creates LTS/#.#.X branch
   --type hotfix    - Creates hotfix/#.#.# branch
   --type release   - Creates release branch
 Arguments:
   --version <version> (optional)


> ci create-branch --type (hotfix, lts, release) --version <version>

### Update Version
 Update the project version to the next one (patch version for LTS, minor version for all others).
 Options:
   --no-commit       - Only update the file without committing.
   --snapshot        - Increments the snapshot version. 
   --release         - Use this option on create release step.
   --grow-changelog  - Updates changelog by inserting EDNAR-style template instead of resetting it to the regular one.
 Args:
   1  - Project file.
  [2] - Changelog file.


> ci update-version --lang (csharp, js, kotlin, python) --project-file <package.json, pom.xml, setup.py> --changelog <changelog.md> [--no-commit] [--release|--snapshot] [--grow-changelog]

### Finalise Version 
 * Finalise release version by removing SNAPSHOT, next, etc.
 * Tag and push the commit to a branch named `release`.
 * A new entry of changelog is added when command is specified.
 Options:
   --no-commit     - Only update the file without committing.
 Args:
   1  - Project file.
  [2] - EDNAR-style changelog file.


> ci finalise-version --lang (csharp, js, kotlin, python) [--no-commit] --project-file <package.json, pom.xml, setup.py> --changelog <changelog.md>

