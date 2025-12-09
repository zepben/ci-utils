#!/bin/bash
# Check to make sure commit has not been released, last build was successful and notify team via Slack that release pipeline has been triggered.
# Environment Variables:
#   BITBUCKET_STEP_TRIGGERER_UUID or GITHUB_ACTOR
#   BITBUCKET_BRANCH or GITHUB_REF
#   BB_AUTH_USERNAME
#   BB_AUTH_PASSWORD

source "$(dirname "$0")/common.sh"

allOptions=( "${build_lang_options[@]}" "${java_build_tool_options[@]}")
get_params $@

debug "Options=${options[@]}"
debug "BITBUCKET_STEP_TRIGGERER_UUID: $BITBUCKET_STEP_TRIGGERER_UUID"
debug "GITHUB_ACTOR: $GITHUB_ACTOR"
debug "GITHUB_REF: $GITHUB_REF"
debug "BITBUCKET_BRANCH: $BITBUCKET_BRANCH"

# mandatory variables
ACTOR=${BITBUCKET_STEP_TRIGGERER_UUID:=${GITHUB_ACTOR:?'No actor was found, was this run in github or bitbucket?'}}
BRANCH=${BITBUCKET_BRANCH:=${GITHUB_REF:?'Branch ref was missing, was this run in github or bitbucket?'}}
file=${args[0]:?'File variable missing.'}

build_lang ${options[@]}

run git config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
run git fetch --tags origin

info "$BRANCH"
info "Checking to make sure commit has not been already released."
current_commit_id=$(git rev-parse HEAD)
for tag in $(git tag -l --sort=-v:refname)
do
    commit_released=$(git rev-list $tag | grep $current_commit_id || true)
    if [[ ! -z $commit_released  ]]; then
        fail "Can't run release pipeline. This commit '$current_commit_id' is part of the [$tag] release."
    elif [[ $tag =~ [v]?${sem_version} ]]; then
        fail "Can't run release pipeline. There is already a tag for ${tag}."
    fi
done

info "Clearing the 'release' branch if it exists"
clear_release_breanch

# Get user name
if [[ -z "$BITBUCKET_STEP_TRIGGERER_UUID" ]]; then
  USERNAME=$(curl -s -X GET -g "https://api.bitbucket.org/2.0/users/${BITBUCKET_STEP_TRIGGERER_UUID}" | jq --raw-output '.display_name')
else
  USERNAME=$ACTOR
fi

run bash $(dirname "$0")/slack-notification.sh "Release has been triggered for $BRANCH by *$USERNAME*."
