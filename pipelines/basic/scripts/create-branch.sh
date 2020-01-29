#!/bin/bash
# Create the LTS/hotfix branch
# Options:
#   --lts       - Creates LTS/#.#.X branch
#   --hotfix    - Creates hotfix/#.#.# branch
# Environment Variables:
#   BB_AUTH_STRING
#   BITBUCKET_REPO_FULL_NAME
#   BITBUCKET_REPO_SLUG
#   BITBUCKET_COMMIT

source "$(dirname "$0")/common.sh"

create_branch_options=( "--lts" "--hotfix" )
allOptions=( "${create_branch_options[@]}" )
get_params $@

debug "Options=${options[@]}"
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
if [[ ! $version =~ [0-9]+.[0-9]+.[0-9]+ ]]; then
    fail "Could not create branch due to tag not having #.#.# format."
fi

info "$version - $BITBUCKET_COMMIT"

IFS='.' read -r -a array <<< "$version"

next_version="${array[0]}.${array[1]}.$((++array[2]))"
info "Next version: $next_version"
if [[ ! -z $(git ls-remote --tags origin | grep "refs/tags/v${next_version}" || true) ]]; then
    fail "$BITBUCKET_COMMIT commit is not the newest tag for ${array[0]}.${array[1]}.X."
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
run git remote set-url origin "https://${BB_AUTH_STRING}@bitbucket.org/$BITBUCKET_REPO_FULL_NAME"

info "Creating branch..."
run git checkout $BITBUCKET_COMMIT -b $branch_name
# Slack notification
run bash $(dirname "$0")/slack-notification.sh "Created branch <https://bitbucket.org/$BITBUCKET_REPO_FULL_NAME/branch/$branch_name|$branch_name> on *<https://bitbucket.org/$BITBUCKET_REPO_FULL_NAME|$BITBUCKET_REPO_SLUG>*."

success "Branch $branch_name creation successful."