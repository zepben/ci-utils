#!/bin/bash
# Create the LTS/hotfix branch
# Options:
#   --lts       - Creates LTS/#.#.X branch
#   --hotfix    - Creates hotfix/#.#.# branch
# Arguments:
#   1 - Version (optional)
# Environment Variables:
#   BB_AUTH_STRING
#   BITBUCKET_REPO_FULL_NAME
#   BITBUCKET_REPO_SLUG
#   BITBUCKET_COMMIT
# Note: When argument is passed it is assumed that Github is used, otherwise it is Bitbucket and the Environment variables are required.

source "$(dirname "$0")/common.sh"

create_branch_options=( "--lts" "--hotfix" )
allOptions=( "${create_branch_options[@]}" )
get_params $@

debug "Options=${options[@]}"

if [[ -z ${args[0]} ]]; then
    debug "BITBUCKET_REPO_FULL_NAME=$BITBUCKET_REPO_FULL_NAME"
    debug "BITBUCKET_REPO_SLUG=$BITBUCKET_REPO_SLUG"
    debug "BITBUCKET_COMMIT=$BITBUCKET_COMMIT"

    # mandatory variables
    BB_AUTH_STRING=${BB_AUTH_STRING:?'Repo auth variable missing.'}
    BITBUCKET_REPO_FULL_NAME=${BITBUCKET_REPO_FULL_NAME:?'Repo full name variable missing.'}
    BITBUCKET_REPO_SLUG=${BITBUCKET_REPO_SLUG:?'Repo slug variable missing.'}
    BITBUCKET_COMMIT=${BITBUCKET_COMMIT:?'Commit variable missing.'}

    # Get tag reference from commit hash
    commit_tag=$(git ls-remote --tags origin | grep "^$BITBUCKET_COMMIT" || true)
    if [[ -z $commit_tag ]]; then
        fail "$BITBUCKET_COMMIT commit has not been tagged."
    fi
    version=$(echo $commit_tag | grep -o refs/tags/.* | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\+" || true)
    COMMIT_ID=$BITBUCKET_COMMIT

    run git remote set-url origin "https://${BB_AUTH_STRING}@bitbucket.org/$BITBUCKET_REPO_FULL_NAME"
else
    debug "1=${args[0]}"
    version=${args[0]}
    tag=$(git tag -l | grep "v$version[.0-9]*" | tail -1)
    version=${tag/v/}
    COMMIT_ID=$(git rev-list -n 1 $tag)
fi

if [[ ! $version =~ [0-9]+.[0-9]+.[0-9]+ ]]; then
    fail "Could not create branch due to tag ($version) not having #.#.# format."
fi

info "$version - $COMMIT_ID"

IFS='.' read -r -a array <<< "$version"

next_version="${array[0]}.${array[1]}.$((++array[2]))"
info "Next version: $next_version"
if [[ ! -z $(git ls-remote --tags origin | grep "refs/tags/v${next_version}" || true) ]]; then
    fail "$version is not the latest tag for ${array[0]}.${array[1]}."
fi

lts_branch_name="LTS/${array[0]}.${array[1]}.X"
if [[ ! -z $(git ls-remote --heads origin | grep $lts_branch_name || true) ]]; then
    fail "There is already a LTS branch named $lts_branch_name."
fi

hotfix_branch_name="hotfix/${next_version}"
if [[ ! -z $(git ls-remote --heads origin | grep $hotfix_branch_name || true) ]]; then
    fail "There is already a hotfix branch named $hotfix_branch_name."
fi

if [[ " ${options[@]} " =~ " --lts " ]]; then
    branch_name=$lts_branch_name
elif [[ " ${options[@]} " =~ " --hotfix " ]]; then
    branch_name=$hotfix_branch_name
fi

run git config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
run git fetch --tags origin

info "Creating branch..."
run git checkout $COMMIT_ID -b $branch_name
# Slack notification
run bash $(dirname "$0")/slack-notification.sh "Created branch $branch_name."

success "Branch $branch_name creation successful."