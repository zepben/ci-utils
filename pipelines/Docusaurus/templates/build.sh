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

# Check that site-config.json is provided
release_notes="./site-config/release-notes.md"
if [ -f "${release_notes}" ]; then
    docusaurus3="yes"
    # We're building Docusaurus 3
    echo 
    echo "####################################"
    echo "#  Building docs with Docusaurus3  #"
    echo "####################################"
    echo 
else
    # We're building Docusaurus 2
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


    # repo will be fetched from environment variable REPO_NAME (if there) or "local-test-docs"
    if [ ! -z "${REPO_NAME}" ]; then
        repo=$(echo ${REPO_NAME} | cut -f2 -d\/)
    else
        repo="local-test-docs"
    fi

    # title needs to be fetched from CI's repo environment, for local we'll use "Docs in test"
    title=${REPO_DOCS_TITLE:-"Docs in test"}

    echo "Filling templates with title '$title' and repo name '$repo'"
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
