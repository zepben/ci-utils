#!/usr/bin/env bash

scripts=$(dirname "$(realpath $0)")

# We assume that the docs folder is mounted under CURRENT directory.
# Container will try to use /docs (easy for local builds)
# CI will use whatever . is

docs=$(pwd)
site_dir=$(pwd)
release_notes="${docs}/site-config/release-notes.md"

# Lazily parse args
for arg in "$@"; do
  case "$arg" in
    "--skip-build")
      skip_build="yes"
      ;;
    "--skip-templates")
      skip_templates="yes"
      ;;
  esac
done

function detect_version() {
    if [ -f "${release_notes}" ]; then
        docusaurus3="yes"
        site_dir="${docs}/site-config"
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
}

function copy_templates() {
    # if running on CI/local job, move the templates to the site-config
    if [[ "${skip_templates}" != "yes" ]]; then
        cp -r /templates/* ${site_dir}/
    fi
}

function configure_site() {
    pushd "${site_dir}"

    # parse templates
    # if testing, and you've forgot to copy templates, error out
    if [ ! -f package.json.template ]; then
        echo "If you're running locally, copy the templates here first and rerun. Otherwise, something went wrong, talk to CI people"
        exit 1
    fi


    # repo will be fetched from environment variable REPO_NAME (if there) or "local-test-docs"
    if [ ! -z "${REPO_NAME}" ]; then
        # cut the ".*/" before the repo name, ie "octopus/zepben" becomes "zepben"
        component=${REPO_NAME#*/}
    else
        component="local-test-docs"
    fi

    # title needs to be fetched from CI's repo environment, for local we'll use "Docs in test"
    title=${DOCS_TITLE:-"Docs in test"}

    echo "Filling templates with title '$title' and repo name '$component'"
    sed -e "s/{title}/${title}/g" -e "s/{component}/${component}/g" $scripts/docusaurus.config.js.template > ./docusaurus.config.js
    sed -e "s/{component}/${component}/g" $scripts/package.json.template > ./package.json

    # cp previous versions
    # docusaurus will create versioned_docs links instead of actual folders, so we'll need to copy them
    # back to the archive folder with link dereference. We'll do this in docusaurus-action. That's why we don't use links here.
    cp -r ../archive/* .

    # link the current docs, it works fine
    ln -s ../docs .

    # link the release-notes
    pushd src/pages
    ln -s ../../release-notes.md .
    popd

    # cleanup
    rm -rf *template*
    rm -rf build.sh

    # go pack to main docs
    popd
}

detect_version
if [ "${docusaurus3}" = "yes" ]; then
    copy_templates
    configure_site
fi

if [ "${skip_build}" != "yes" ]; then 
    cd "${site_dir}"
    npm ci
    npm run build
fi
