#!/bin/bash
# Deploy

source "$(dirname "$0")/common.sh"

allOptions=( "${release_options[@]}" )
get_params $@

debug "Options=${options[@]}"
debug "1=${args[0]}"

file=${args[0]:?'project missing.'}

build_lang ${options[@]}

deploy_lib

# Slack notification
run bash $(dirname "$0")/slack-notification.sh "Deployed $version."