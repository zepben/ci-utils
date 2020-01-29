#!/bin/bash
# Make sure version is not snapshot and has not been released.
# Options:
#   See build_lang_options and java_build_tool_options in ../../scripts/common.sh
# Args:
#   1 - project file.

source "$(dirname "$0")/common.sh"
allOptions=( "${finalize_project_options[@]}" )
get_params $@

debug "Options=${options[@]}"
debug "1=${args[0]}"

file=${args[0]:?'File variable missing.'}

build_lang ${options[@]}
info "Checking if version is for release..."
check_release_version

info "Checking if Git tag already exists..."
check_tag_exists $version