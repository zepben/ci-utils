#!/bin/bash
# Update the project version to the next one (patch version for LTS, minor version for all others).
# Options:
#   See build_lang_options and java_build_tool_options in ../../scripts/common.sh
#   --no-commit       - Only update the file without commiting.
#   --snapshot        - Increments the snapshot version. Only useful for C# and Python, ie 1.0.0-pre1, 1.0.0b1. Java doesn't have this concept.
#   --release         - Use this option on create release step.
#   --grow-changelog  - Updates changelog by inserting EDNAR-style template instead of resetting it to the regular one.
# Args:
#   1  - Project file.
#  [2] - Changelog file.
# Environment Variables:
#   BITBUCKET_BRANCH/GITHUB_REF

source "$(dirname "$0")/common.sh"

allOptions=( "${update_project_options[@]}" )
get_params $@

debug "Options=${options[@]}"
debug "1=${args[0]}"
debug "2=${args[1]}"

if [[ ! " ${options[@]} " =~ " --no-commit " ]]; then
    run git config remote.origin.fetch "+refs/heads/*:refs/remotes/origin/*"
    run git fetch --all
fi

BRANCH=${BITBUCKET_BRANCH:=${GITHUB_REF:?'Branch ref was missing, was this run in github or bitbucket?'}}
BRANCH=${BRANCH/refs\/heads\//}
info "Branch: $BRANCH"
if [[ " ${options[@]} " =~ " --release " && $BRANCH = *"hotfix/"* ]]; then
    run git push origin -d $BRANCH
    if [[ ! -z $(git branch -a | grep remotes/origin/release) ]]; then
        run git push origin -d release
    fi
    exit 0
fi

file=${args[0]:?'File variable missing.'}

# optional variables
changelog=${args[1]}

# Update project version
info "Updating version..."
if [[ " ${options[@]} " =~ " --snapshot " ]]; then
    build_lang ${options[@]}
    update_snapshot_version
else
    # Checkout release branch
    if [[ ! " ${options[@]} " =~ " --no-commit " ]]; then
        if [[ " ${options[@]} " =~ " --release " ]]; then
            if [[ -z $(git branch -a | grep remotes/origin/release) ]]; then
                run git checkout -b release
            else
                run git checkout release
            fi
        else
            run git checkout $BRANCH
        fi
    fi
    build_lang ${options[@]}

    # Determine which version to update
    if [[ $BRANCH = "LTS/"* || $BRANCH = "hotfix/"* ]]; then
        version_type="patch"
    else
        version_type="minor"
    fi

    update_version
fi

# Update changelog
release_notes_template="### Breaking Changes\n* None.\n\n### New Features\n* None.\n\n### Enhancements\n* None.\n\n### Fixes\n* None.\n\n### Notes\n* None.\n"
if [[ ! -z $changelog ]]; then
    grow_changelog_format=$(egrep "## \[[0-9]+\.[0-9]+\.[0-9]+" $changelog)
    if [[ " ${options[@]} " =~ " --grow-changelog " || ! -z $grow_changelog_format ]]; then
        info "Inserting template into changelog..."
        sed -i "/^# .*/a ## [${new_version/-SNAPSHOT*/}] - UNRELEASED\n$release_notes_template" $changelog
    else
        info "Resetting changelog to template..."
        rm -f $changelog && touch $changelog
        printf "## v${new_version/-SNAPSHOT*/}\n\n$release_notes_template" >> $changelog
    fi
fi

# commit changes
stage_file $file
stage_file $changelog

# Show status for debugging
git status

if [[ ! " ${options[@]} " =~ " --no-commit " ]]; then
    if [[ ! -z $BITBUCKET_REPO_FULL_NAME ]]; then
        git remote set-url origin "https://${BB_AUTH_STRING}@bitbucket.org/$BITBUCKET_REPO_FULL_NAME"
    fi

    if [[ " ${options[@]} " =~ " --release " ]]; then
        commit_update_version
        run git checkout $BRANCH
        run git pull origin release
        run git push origin $BRANCH
        run git push origin -d release
    else
        commit_update_version $BRANCH
    fi
fi
