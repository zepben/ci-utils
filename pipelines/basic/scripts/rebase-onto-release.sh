#!/bin/bash
# * Rebase the branch on top of release branch and delete release branch. 
# * Notify the team via Slack whether it has completed the merge or needs human intervention.
# Environment Variables:
#   BB_AUTH_STRING
#   BITBUCKET_REPO_FULL_NAME
#   BITBUCKET_REPO_SLUG
#   BITBUCKET_BRANCH

source "$(dirname "$0")/common.sh"

debug "BB_AUTH_STRING=$BB_AUTH_STRING"
debug "BITBUCKET_REPO_FULL_NAME=$BITBUCKET_REPO_FULL_NAME"
debug "BITBUCKET_REPO_SLUG=$BITBUCKET_REPO_SLUG"
debug "BITBUCKET_BRANCH=$BITBUCKET_BRANCH"

# mandatory variables
BB_AUTH_STRING=${BB_AUTH_STRING:?'Repo auth variable missing.'}
BITBUCKET_REPO_FULL_NAME=${BITBUCKET_REPO_FULL_NAME:?'Repo full name variable missing.'}
BITBUCKET_REPO_SLUG=${BITBUCKET_REPO_SLUG:?'Repo slug variable missing.'}
BITBUCKET_BRANCH=${BITBUCKET_BRANCH:?'Repo branch variable missing.'}

# Checkout current branch
# run git config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
# run git fetch --tags origin

# branch=$(bash /scripts/get-branch-name.sh $BITBUCKET_BRANCH)
# branch=${branch:?'Branch must be master or LTS.'}

info "Current branch: $BITBUCKET_BRANCH"
run git checkout $BITBUCKET_BRANCH

if [[ $BITBUCKET_BRANCH = "hotfix/"* ]]; then
    info "Skipping rebase."
    exit 0;
fi

# Rebase current branch
info "Rebasing branch..."
run set +e
run git rebase origin/release
run set -e

if [[ $? == 0 ]]; then
    run git remote set-url origin "https://${BB_AUTH_STRING}@bitbucket.org/$BITBUCKET_REPO_FULL_NAME"
    run git push origin -f $branch
    run bash $(dirname "$0")/slack-notification.sh "*<https://bitbucket.org/$BITBUCKET_REPO_FULL_NAME|$BITBUCKET_REPO_SLUG>* - Rebased $branch on latest release."
    run git push origin -d release
    success "Rebase successful."
else
    run bash $(dirname "$0")/slack-notification.sh "*<https://bitbucket.org/$BITBUCKET_REPO_FULL_NAME|$BITBUCKET_REPO_SLUG>* - Failed to rebase $branch. Please manually rebase master on top of <https://bitbucket.org/$BITBUCKET_REPO_FULL_NAME/branch/release|release>."
    fail "Rebase failed."
fi