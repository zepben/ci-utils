#!/bin/bash

source "$(dirname "$0")/common.sh"

allOptions=( "${build_options[@]}" )
get_params $@

file=${args[0]:?'File variable missing.'}

build_lang ${options[@]}

run_build