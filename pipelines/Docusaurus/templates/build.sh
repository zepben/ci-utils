#!/usr/bin/env bash

scripts=$(dirname "$(realpath $0)")

# Lazily parse args
if [[ "$1" == "--skip-build" || "$2" == "--skip-build" ]]; then 
    skip_build="yes"
fi

if [[ "$1" == "--skip-templates" || "$2" == "--skip-templates" ]]; then 
    skip_templates="yes"
fi

# We assume that the docs folder is mounted under CURRENT directory.
# Container will try to use /docs (easy for local builds)
# CI will use whatever . is

# site-config.json provides the values that we put into the package.json and docusaurus.config.js
# These values in most cases are just the name of the project, slug (where to access it in the doco site) 
# and the "project" meta tag. 

# Check that site-config.json is provided
release_notes="./site-config/release-notes.md"
if [ -f ./site-config/site-config.json ]; then
    docusaurus3="yes"
    # We're building Docusaurus 3

    echo 
    echo "####################################"
    echo "#  Building docs with Docusaurus3  #"
    echo "####################################"
    echo 
else
    echo 
    echo "####################################"
    echo "#  Building docs with Docusaurus2  #"
    echo "####################################"
    echo 
fi

if [ "${docusaurus3}" = "yes" ]; then
    cd site-config

    # we want to keep working with release-notes in src/pages/release-notes
    # but also have stuff in src/ templated.
    # so here we move release-notes aside, restore templates and move them back.

    # if running CI/local job, move the templates and place release-notes in src/pages for the build
    if [[ -d /templates && "${skip_templates}" != "yes" ]]; then
        cp -r /templates/* .
    fi

    # Move release-notes back
    # mv release-notes.md "${release_notes}"

    # parse templates
    # if testing, and you've forgot to copy templates, error out
    if [ ! -f package.json.template ]; then
        echo "If you're running locally, copy the templates here first and rerun. Otherwise, something went wrong, talk to CI people"
        exit 1
    fi
    eval "$(jq -r 'to_entries[] | "export \(.key)=\"\(.value)\""' site-config.json)"

    # repo=$(gh repo view --json "name" -q '.name')
    repo="mvn-lib-ci-test"
    sed -e "s/{title}/${title}/g" -e "s/{slug}/${repo}/g" -e "s/{projectName}/${repo}/g" $scripts/docusaurus.config.js.template > ./docusaurus.config.js
    sed -e "s/{projectName}/${repo}/g" $scripts/package.json.template > ./package.json

    # link previous versions
    ln -s ../archive/* .

    # link the current docs
    ln -s ../docs .

    # Place release-notes
    cp release-notes.md src/pages/release-notes.md

    # cleanup
    rm -rf *template*
    rm -rf build.sh

    # go pack to main docs
    cd ..
fi

if [ "${skip_build}" != "yes" ]; then 
    if [ "${docusaurus3}" = "yes" ]; then
        cd site-config
    fi
    npm ci
    npm run build
fi
