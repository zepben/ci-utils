#!/bin/bash

if [ ! -f "$file" ]; then
    fail "$file is not present."
fi

version=$(sed -nE 's/^version:[[:space:]]*([0-9]+\.[0-9]+\.[0-9]+(-beta\.[0-9]+)?)[[:space:]]*$/\1/p' $file)
sem_version=${version%-beta.*}
info "Version: $version"
info "Sem Version: $sem_version"

run_build() {
    fail "Dart build not implemented."
}

deploy_lib(){
    fail "Dart deploy_lib not implemented."
}

write_new_version(){
    old_version=${1:? 'Old version is required.'}
    new_version=${2:? 'New version is required.'}

    if [[ $old_version != $new_version ]]; then
        info "Writing new version $new_version..."
        run sed -i "s/^version:[[:space:]]*$old_version[[:space:]]*$/version: $new_version/" $file
    fi
}

update_version(){
    incr_version $version_type $version
    write_new_version $version "${new_version}-beta.1"
}

update_snapshot_version(){
    new_version=${version%-beta.*}
    beta=${version##*-beta.}
    beta=$((++beta))
    write_new_version $version "${new_version}-beta.${beta}"
}

find_unreleased_version() {
    unreleased_version=${new_version/-beta.*/}
}

finalize_version(){
    new_version=${version%-beta.*}
    write_new_version "$version" "$new_version"
}

package(){
    fail "package for dart not yet implemented."
}

check_release_version(){
    fail "Dart check_release_version Not implemented."
}
