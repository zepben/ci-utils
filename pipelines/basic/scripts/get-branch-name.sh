#!/bin/bash
# Prints the branch name of the commit if not supplied
# Required args:
#   1 - branch

source "$(dirname "$0")/common.sh"

debug "branch=$1"

branch=$1

current_commit_id=$(git rev-parse HEAD)
if [[ -z $branch ]]; then
    for br in $(git branch -r | egrep -h "^\s*origin/master$|LTS" | awk '{$1=$1};1')
    do
        commit_in_branch=$(git rev-list $br | grep $current_commit_id || true)
        if [[ ! -z $commit_in_branch  ]]
        then
            echo $br | awk '{sub(/origin\//,""); print}'
        fi
    done
else
    echo "$branch"
fi