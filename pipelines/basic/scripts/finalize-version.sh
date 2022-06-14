#!/bin/bash
# * Finalize release version by removing SNAPSHOT, next, etc.
# * Tag and push the commit to a branch named release.
# * A new entry of changelog is added when command is specified.
# Options:
#   See build_lang_options and java_build_tool_options in ../../scripts/common.sh
#   --no-commit     - Only update the file without committing.
# Args:
#   1  - Project file.
#  [2] - Changelog file.
#  [3] - Update changelog command (required if changelog file is specified).
# Environment Variables:
#   BITBUCKET_BRANCH

source "$(dirname "$0")/common.sh"

allOptions=( "${finalize_project_options[@]}" )
get_params $@

debug "Options=${options[@]}"
debug "1=${args[0]}"
debug "2=${args[1]}"
debug "3=${args[@]:2}"

file=${args[0]:?'File variable missing.'}

# optional variables
changelog=${args[1]}
update_changelog_command=${args[@]:2}

if [[ ! " ${options[@]} " =~ " --no-commit " ]]; then
    run git checkout -b release
fi

build_lang ${options[@]}
# Finalize version
info "Finalizing version..."
finalize_version

# Update changelog
if [[ ! -z $changelog ]]; then
    info "Updating changelog..."
    if [[ -z $update_changelog_command ]]; then
        fail "Need to specify command to update changelog when changelog parameter is specified."
    fi
    run_eval $update_changelog_command $changelog
fi

# commit changes
stage_file $file
stage_file $changelog

if [[ ! " ${options[@]} " =~ " --no-commit " ]]; then
    check_tag_exists $new_version
    commit_finalize_version
fi