#!/usr/bin/env bash

scripts=$(dirname "$(realpath $0)")


# We assume that the docs folder is mounted under current directory.
# Container will try to use /docs (easy for local builds)
# CI will use whatever . is

# site-config.json provides the values that we put into the package.json and docusaurus.config.js
# These values in most cases are just the name of the project, slug (where to access it in the doco site) 
# and the "project" meta tag. 

# Check that site-config.json is provided
release_notes="./src/pages/release-notes.md"
if [ -f site-config.json ]; then
    # We're building Docusaurus 3

    if [ ! -f release-notes.md ]; then
        echo "The file release-notes.json seems to be missing! Please check and try again!" 
        exit 1
    fi

    # Move the templates and place release-notes in src/pages
    cp -r /templates/* .
    cp release-notes.md "${release_notes}"

    # parse templates
    eval "$(jq -r 'to_entries[] | "export \(.key)=\"\(.value)\""' site-config.json)"
    sed -e "s/{title}/${title}/g" -e "s/{slug}/${slug}/g" -e "s/{projectName}/${projectName}/g" $scripts/docusaurus.config.js.template > ./docusaurus.config.js
    sed -e "s/{projectName}/${projectName}/g" $scripts/package.json.template > ./package.json

    # cleanup
    rm -rf *template*
    rm -rf build-docs.sh
fi

if [ "$1" != "skip-build" ]; then 
    npm ci
    npm run build
fi
