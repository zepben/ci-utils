This repo is for creating a custom Docker image that has the scripts for [release management](https://bitbucket.org/zepben/how-tos/src/10d683afbb9ff071e54e5d053879fc655387c160/bitbucket_pipelines/release-management.md).

See [install-dependencies.sh](install-dependencies.sh) to know what tools are included with this image.

**Note** - Set `DEBUG=true` to print debug messages.

## Building the Docker image

Run the `custom: pipeline-basic` pipeline to build this image.

For building locally, see [README.md](../../README.md).

# Commands
Commands are aliases to script files. The aliases are in [install-dependencies.sh](install-dependencies.sh).

### [release-checks](scripts/release-checks.sh) - Checks and notifications before creating the release.

### [create-branch](scripts/create-branch.sh) - Create LTS/Hotfix support branch.

### [rebase](scripts/rebase-onto-release.sh) - Rebases the current branch on top of the latest release branch.

### [azure-devops](scripts/trigger-azure-devops.sh) - Trigers Azure DevOps to run build.

### [release-docs-source](scripts/release-docs-source.sh) - Zip and upload docs directory.

## Language specific commands
The commands below are steps specific for parsing and updating programming language project files.

\* = \<lang>[-\<tool\>]

Where lang is the following:

* `cs` - C#
* `js` - Java Script
* `java` - Java
* `py` - Python

Where tool is the following:

* Java
  
    * `mvn`       - Maven
    * `gradle`    - Gradle


### [*-update-version](/scripts/update-version.sh) - Update version for next release.

### [*-finalize-version](/scripts/finalize-version.sh) - Remove snapshot, next, etc. in version.

### [*-check-release-version](/scripts/check-release-version.sh) - Make sure version is not snapshot and has not been released.


## Running Docker locally for testing

docker run -it --env-file D:\Projects\containers-and-vms\pipelines\basic\env.list --mount type=bind,source="D:\Projects\company-super-pom",target="/app" --rm --entrypoint bash mavenrepo.zepben.com:8083/repository/zepben-docker/pipeline-basic:latest