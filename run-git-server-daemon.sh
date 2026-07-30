#!/usr/bin/env bash

# You will need git-daemon installed to serve your local git repos
git daemon --reuseaddr --base-path=. --export-all --enable=receive-pack --verbose