script.sh  --_language_ [options] \<file\>

language:

java (--maven | --gradle)

python

csharp

js

options:

update-version.sh [ --no-commit | --snapshot ]

release-lib.sh [ --snapshot ]

release-app.sh [ --snapshot ] [ --build-docs \<mkdocs config file\> \<docs path\> | --include-docs \<docs path\> ]

Notes: 

* _--include-docs_ option copies content of docs path.

* _--build-docs_ option builds documentation using Mkdocs and copies the built documentation.

* \<mkdocs config file\> and \<docs path\> are relative to the apps directory.

* When _--include-docs_ option is specified, the command parameters becomes _script.sh  --_language_ [options] \<docs path\> \<file\>_. E.g. `release-app.sh --java --maven --include-docs docs pom.xml`

* When _--build-docs_ option is specified, the command parameters becomes _script.sh  --_language_ [options] \<mkdocs config file\> \<docs path\> \<file\>_. E.g. `release-app.sh --java --maven --build-docs docs/mkdocs.yml docs pom.xml`

build.sh [ --no-test ]

finalize-version.sh [ --no-commit ]

# Env vars

DEBUG=true - to enable debug mode

VERSION_TYPE

BITBUCKET_REPO_FULL_NAME

BB_AUTH_STRING = username:password

BITBUCKET_BRANCH

DOCS_BUILDER_TAG

DOCS_BUILDER_REPO=git@bitbucket.org:zepben/docs-builder.git

#### For Slack notification

SLACK_NOTIFICATION = YES/NO

SLACK_WEBHOOK

BITBUCKET_WORKSPACE

BITBUCKET_REPO_SLUG

BITBUCKET_BUILD_NUMBER

# Test
`bash test.sh` to copy all scripts into single location.

docker run -it --env-file D:\Projects\vm-container-images\pipelines\all\env.list --mount type=bind,source="D:\Projects\cimproto",target="/app" --mount type=bind,source="D:\Projects\vm-container-images\pipelines\bin",target="/test_scripts" --rm --entrypoint bash mavenrepo.zepben.com:8083/repository/zepben-docker/pipeline-all