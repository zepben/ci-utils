# Commands

#### release-app - build-release-app.sh
Builds and packs javascript project as final version to repos download section.

#### snapshot-app - build-snapshot-app.sh
Builds and packs javascript project using npm.

#### build - build-test.sh
Build and test source codes.

#### update-version [options] [changelog update_changelog_command] - update-project-version.sh

Note: _update_changelog_command_ is required when changelog is specified.

options:
- `--no-commit` - Will not commit files.

#### finalize-version [options] [changelog update_changelog_command] - finalize-release-version.sh

Note: _update_changelog_command_ is required when changelog is specified.

options:
- `--no-commit` - Will not commit files.

# Env vars
VERSION_TYPE

BITBUCKET_REPO_FULL_NAME

BB_AUTH_STRING = username:password

MKDOCS_BUILD = true/false

NPM_TOKEN = api auth token

#### For Slack notification

SLACK_NOTIFICATION = YES/NO

SLACK_WEBHOOK

BITBUCKET_WORKSPACE

BITBUCKET_REPO_SLUG

BITBUCKET_BUILD_NUMBER

BITBUCKET_REPO_FULL_NAME

# Running Docker locally

docker run -it --env-file D:\Projects\containers-and-vms\pipelines\JavaScript\env.list --mount type=bind,source="D:\Projects\web-client",target="/app" --rm --entrypoint bash mavenrepo.zepben.com:8083/repository/zepben-docker/pipeline-node:latest