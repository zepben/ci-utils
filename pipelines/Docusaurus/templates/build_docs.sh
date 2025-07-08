#!/usr/bin/env bash

# We assume that the docs folder is mounted under /docs
cd /docs

# site-config.json provides the values that we put into the package.json and docusaurus.config.js
# These values in most cases are just the name of the project, slug (where to access it in the doco site) 
# and the "project" meta tag. 

# Check that site-config.json is provided
if [ ! -f site-config.json ]; then
    echo "The file site-config.json seems to be missing! Please check and try again!" 
    exit 1
fi

# TODO: move release-notes into the root path
# the reason is that we only need them for build time, not actually in src/pages
# Backup the release-notes
release_notes="./src/pages/release-notes.md"
if [ -f "${release_notes}" ]; then
    cp "${release_notes}" .
    rm -rf src
    rm -rf build
    rm -rf node_modules
fi

# Move the templates and restore release-notes
cp -r /templates/* .
cp release-notes.md "${release_notes}"

eval "$(jq -r 'to_entries[] | "export \(.key)=\"\(.value)\""' site-config.json)"
sed -e "s/{title}/${title}/g" -e "s/{slug}/${slug}/g" -e "s/{project}/${project}/g" docusaurus.config.js.template > ./docusaurus.config.js
sed -e "s/{name}/${name}/g" package.json.template > ./package.json

rm -rf *template*

npm ci
npm run build
