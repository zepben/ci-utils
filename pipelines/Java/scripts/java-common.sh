#!/bin/bash
debug "NEXUS_USERNAME=$NEXUS_USERNAME"
debug "NEXUS_PASSWORD=$NEXUS_PASSWORD"
debug "NEXUS_MAVEN_REPO=$NEXUS_MAVEN_REPO"
debug "NEXUS_MAVEN_RELEASE=$NEXUS_MAVEN_RELEASE"
debug "NEXUS_MAVEN_SNAPSHOT=$NEXUS_MAVEN_SNAPSHOT"


if [ ! -f "$file" ]; then
    fail "$file is not present."
fi

java_build_tool() {
    argv=${@:? 'Build tool option is required.'}
    if [[ " ${argv[@]} " =~ " --maven " ]]; then
        source "$(dirname "$0")/maven.sh"
    elif [[ " ${argv[@]} " =~ " --gradle " ]]; then
        source "$(dirname "$0")/gradle.sh"
    else
        fail "Available build tool is --maven or --gradle."
    fi
}

java_build_tool "${options[@]}"

info "Version: $version"
sem_version=${version/-SNAPSHOT*/}
info "Sem Version: $sem_version"

run_build() {
    java_run_test
}

deploy_lib(){
    if [[ " ${options[@]} " =~ " --snapshot " && $version != *"-SNAPSHOT"* ]]; then
        info "--snapshot option is only for non finalized versions. Skipping deployment."
        exit 0
    fi

    java_deploy
}

package(){
    if [[ " ${options[@]} " =~ " --snapshot " && $version != *"-SNAPSHOT"* ]]; then
        info "--snapshot option is only for non finalized versions. Skipping deployment."
        exit 0
    fi

    java_package
}

write_new_version(){
    old_version=${1:? 'Old version is required.'}
    new_version=${2:? 'New version is required.'}

    if [[ $old_version != $new_version ]]; then
        info "Writing new version $new_version..."
        java_write_new_version "$old_version" "$new_version"
    fi
}

update_version(){
    incr_version $version_type $version
    write_new_version $version "${new_version}-SNAPSHOT1"
}

update_snapshot_version(){
    new_version=${version%-SNAPSHOT*}
    beta=${version##*-SNAPSHOT}
    beta=$((++beta))
    write_new_version $version "${new_version}-SNAPSHOT${beta}"
}

find_unreleased_version() {
    unreleased_version=${new_version/-SNAPSHOT*/}
}

finalize_version(){
    new_version=${version/-SNAPSHOT*/}
    sed -i "s/-SNAPSHOT[0-9]*//g" $file
}

check_release_version(){
    if [[ $version == *"-SNAPSHOT" ]]; then
        fail "Version cannot be snapshot."
    fi
}
