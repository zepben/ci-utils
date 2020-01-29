#!/bin/bash
# Upload docs source to Bitbucket.
# Environment Variables:
#   BB_AUTH_STRING
#   BITBUCKET_REPO_FULL_NAME
#   BITBUCKET_TAG
# Args:
#   1  - Path to docs source.
#   2  - Version.

source "$(dirname "$0")/common.sh"

debug "1=${1}"
debug "2=${2}"
debug "BITBUCKET_REPO_FULL_NAME=$BITBUCKET_REPO_FULL_NAME"
debug "BB_AUTH_STRING=$BB_AUTH_STRING"

docs_path=${1:?'Docs path missing.'}
version=${2:?'Version missing.'}
BITBUCKET_REPO_FULL_NAME=${BITBUCKET_REPO_FULL_NAME:?'Repo full name variable missing.'}
BB_AUTH_STRING=${BB_AUTH_STRING:?'Auth string variable missing.'}

if [ ! -d "$docs_path" ]; then
    fail "$docs_path not found."
fi
cd $docs_path

# Package docs
docsFilename="docs-source-${version}.zip";
run zip -r $docsFilename .

# Upload
info "Uploading docs: $docsFilename..."
run curl -v -X POST --user "${BB_AUTH_STRING}" "https://api.bitbucket.org/2.0/repositories/${BITBUCKET_REPO_FULL_NAME}/downloads" --form files=@"$docsFilename"
