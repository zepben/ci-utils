#!/bin/bash
# * Finalize release version by removing "b", "next", etc.
# * Tag and push the commit to a branch named release.
# * A new entry of changelog is added when command is specified.
# Options:
#   See build_lang_options and java_build_tool_options in ../../scripts/common.sh
#   --no-commit     - Only update the file without committing.
# Args:
#   1  - Project file.
#  [2] - EDNAR-style changelog file.
# Environment Variables:
#   BITBUCKET_BRANCH

source "$(dirname "$0")/common.sh"

allOptions=( "${finalize_project_options[@]}" )
get_params $@

debug "Options=${options[@]}"
debug "1=${args[0]}"
debug "2=${args[1]}"

file=${args[0]:?'File variable missing.'}

# optional variables
changelog=${args[1]}

if [[ ! " ${options[@]} " =~ " --no-commit " ]]; then
    run git checkout -b release
fi

build_lang ${options[@]}
# Finalize version
info "Finalizing version..."
finalize_version

# Update changelog
if [[ ! -z $changelog ]]; then
    info "Timestamping version in changelog..."
    sed -i "s/UNRELEASED/$(date +'%Y-%m-%d')/g" $changelog
fi

# commit changes
stage_file $file
stage_file $changelog

if [[ ! " ${options[@]} " =~ " --no-commit " ]]; then
    check_tag_exists $new_version
    commit_finalize_version
fi
