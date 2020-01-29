#!/bin/bash
# Builds release artifact and docs for an app project.
# Required global:
#   BB_AUTH_STRING
#   BITBUCKET_REPO_FULL_NAME

source "$(dirname "$0")/common.sh"

allOptions=( "${release_app_options[@]}" )
get_params $@

debug "Options=${options[@]}"
debug "1=${args[0]}"
debug "BITBUCKET_REPO_FULL_NAME=$BITBUCKET_REPO_FULL_NAME"
debug "BB_AUTH_STRING=$BB_AUTH_STRING"

# mandatory variables
if [[ " ${options[@]} " =~ " --build-docs " ]]; then
    mkdocs_config=${args[0]:?'Mkdocs config missing.'}
    docs_path=${args[1]:?'Docs path missing.'}
    file=${args[2]:?'project missing.'}
elif [[ " ${options[@]} " =~ " --include-docs " ]]; then
    docs_path=${args[0]:?'Docs path missing.'}
    file=${args[1]:?'project missing.'}
else
    file=${args[0]:?'project missing.'}
fi

BITBUCKET_REPO_FULL_NAME=${BITBUCKET_REPO_FULL_NAME:?'Repo full name variable missing.'}
BB_AUTH_STRING=${BB_AUTH_STRING:?'Auth string variable missing.'}

build_lang ${options[@]}

# Package
info "Building artifact..."
package

# zip package
if [[ $src == *"/" ]]; then 
    filename="${PWD}/${artifactName}.zip"
    cd $src
    run zip -r $filename .
else
    filename=${src}
fi

# Upload
info "Uploading artifact: $filename..."
run curl -v -X POST --user "${BB_AUTH_STRING}" "https://api.bitbucket.org/2.0/repositories/${BITBUCKET_REPO_FULL_NAME}/downloads" --form files=@"$filename"

# Slack notification
filename=$(basename $filename)
run bash $(dirname "$0")/slack-notification.sh "$version is available. <https://bitbucket.org/${BITBUCKET_REPO_FULL_NAME}/downloads/$filename|Download>"

if [[ " ${options[@]} " =~ --.*-docs ]]; then
    # Docs
    if [[ " ${options[@]} " =~ " --build-docs " ]]; then
        run git clone --branch $DOCS_BUILDER_TAG $DOCS_BUILDER_REPO docs-builder
        run cd docs-builder/
        run python3 -m pip install -r requirements.txt
        run python3 build.py -c -f $mkdocs_config -d $docs_path ../
        run cd ..
        run cp -r docs-builder/site/* build/docs/
    elif [[ " ${options[@]} " =~ " --include-docs " ]]; then
        cd $docs_path
    fi

    # Package docs
    docsFilename="docs-source-${version}.zip";
    run zip -r $docsFilename .

    # Upload
    info "Uploading docs: $docsFilename..."
    run curl -v -X POST --user "${BB_AUTH_STRING}" "https://api.bitbucket.org/2.0/repositories/${BITBUCKET_REPO_FULL_NAME}/downloads" --form files=@"$docsFilename"
fi