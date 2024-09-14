#!/bin/bash

if [ ! -f "$file" ]; then
    fail "$file is not present."
fi

version=$(jq -r .version $file)
sem_version=${version%-next*}
info "Version: $version"
info "Sem Version: $sem_version"

run_build() {
    run npm ci --unsafe-perm
    run npm run lint-src
    run npm run test-ci
}

deploy_lib(){
    if [[ " ${options[@]} " =~ " --snapshot " && $version != *"-next"* ]]; then
        info "--snapshot option is only for non finalized. Skipping deployment."
        exit 0
    fi

    run npm pack
    run npm publish
}

package(){
    if [[ " ${options[@]} " =~ " --snapshot " && $version != *"-next"* ]]; then
        info "--snapshot option is only for non finalized versions. Skipping deployment."
        exit 0
    fi

    if [[ ! " ${options[@]} " =~ " --no-build " ]]; then
        run npm ci --unsafe-perm
        run npm run prod
    fi

    artifactId=$(jq -r .name $file)
    artifactName="${artifactId}-${version}"
    src="dist/"
}

write_new_version(){
    old_version=${1:? 'Old version is required.'}
    new_version=${2:? 'New version is required.'}

    if [[ $old_ver != $new_ver ]]; then
        info "Writing new version $new_version..."
        run jq --arg VERSION $new_version '.version = $VERSION' $file
        run cp -f $output_file $file
    fi
}

update_version(){
    incr_version $version_type $version
    write_new_version $version "${new_version}-next1"
}

update_snapshot_version(){
    new_version=${version%-next*}
    beta=${version##*-next}
    beta=$((++beta))
    write_new_version $version "${new_version}-next${beta}"
}

finalize_version(){
    new_version=${version//-next*/}
    write_new_version "$version" "$new_version"

    sed -i "s/-next[0-9]\+//g" $file
}

check_release_version(){
    fail "Js check_release_version Not implemented."
}
