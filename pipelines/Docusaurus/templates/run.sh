#!/usr/bin/env bash

# We assume that the docs folder is mounted under CURRENT directory.
site_dir=$(pwd)/site-config

# Lazily parse the command
pushd "${site_dir}"
npm run $1
popd
