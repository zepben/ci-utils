#!/bin/bash

debug "ZEPBEN_PYPI_REPO=$ZEPBEN_PYPI_REPO"
debug "ZEPBEN_PYPI_USERNAME=$ZEPBEN_PYPI_USERNAME"
debug "ZEPBEN_PYPI_PASSWORD=$ZEPBEN_PYPI_PASSWORD"

ZEPBEN_PYPI_REPO=${ZEPBEN_PYPI_REPO:?'Maven repo username variable missing.'}
ZEPBEN_PYPI_USERNAME=${ZEPBEN_PYPI_USERNAME:?'Maven repo password variable missing.'}
ZEPBEN_PYPI_PASSWORD=${ZEPBEN_PYPI_PASSWORD:?'Maven repo url variable missing.'}

if [ ! -f "$file" ]; then
    fail "$file is not present."
fi

version="$(cat $file | grep 'version[[:space:]]*=[[:space:]]*"\?[0-9]\+\.[0-9]\+\.[0-9]\+\(b[0-9]\+\)\?"\?' | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\+\(b[0-9]\+\)\?")"
sem_version=${version%b*}
info "Version: $version"
info "Sem Version: $sem_version"

run_build() {
    fail "Python does not need to be built."
}

deploy_lib(){
    if [[ " ${options[@]} " =~ " --snapshot " && $version != *"b"* ]]; then
        info "--snapshot option is only for non finalized. Skipping deployment."
        exit 0
    fi

    run python $file sdist
    run twine upload --repository-url "$ZEPBEN_PYPI_REPO" -u "$ZEPBEN_PYPI_USERNAME" -p "$ZEPBEN_PYPI_PASSWORD" dist/*
}

write_new_version(){
    old_ver=${1:? 'Old version is required.'}
    new_ver=${2:? 'New version is required.'}

    if [[ $old_ver != $new_ver ]]; then
        info "Writing new version $new_ver..."
        run sed -i "/version[[:space:]]*=[[:space:]]*/s/$old_ver/$new_ver/" $file
    fi
}

update_version(){
    incr_version $version_type $version
    write_new_version $version "${new_version}b1"
}

update_snapshot_version(){
    new_version=${version%b*}
    beta=${version##*b}
    beta=$((++beta))
    write_new_version $version "${new_version}b${beta}"
}

finalize_version(){
    new_version=${version%b*}
    write_new_version "$version" "$new_version"
}

package(){
    fail "package for python not yet implemented."
}

check_release_version(){
    fail "Py check_release_version Not implemented."
}