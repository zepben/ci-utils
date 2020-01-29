#!/bin/bash

info "build tool: gradle"
debug "NEXUS_USERNAME=$NEXUS_USERNAME"
debug "NEXUS_PASSWORD=$NEXUS_PASSWORD"
debug "NEXUS_MAVEN_REPO=$NEXUS_MAVEN_REPO"
debug "NEXUS_MAVEN_RELEASE=$NEXUS_MAVEN_RELEASE"
debug "NEXUS_MAVEN_SNAPSHOT=$NEXUS_MAVEN_SNAPSHOT"

NEXUS_USERNAME=${NEXUS_USERNAME:?'Maven repo username variable missing.'}
NEXUS_PASSWORD=${NEXUS_PASSWORD:?'Maven repo password variable missing.'}

properties="/root/.gradle/gradle.properties"
info "Gradle properties: $properties"

if [[ "$file" != *".gradle" ]]; then
    fail "File $file needs to be gradle."
fi

version="$(cat $file | grep "^version\( \)\?\(=\)\?\( \)\?'\?[0-9]\+\.[0-9]\+\.[0-9]\+\(\-SNAPSHOT\)\?'\?" | grep -o "[0-9]\+\.[0-9]\+\.[0-9]\+\(\-SNAPSHOT\)\?")"

set_nexus_repo_props() {
    if [ ! -f "$properties" ]; then
        run mkdir -p "${properties%/*}"
        run touch "$properties"
    fi
    username_key=$(cat $properties | grep "nexusUsername" || true)
    if [ -z $username_key ]; then
        debug "Writing nexusUsername to $properties."
        echo "nexusUsername=$NEXUS_USERNAME" >> $properties
    fi
    password_key=$(cat $properties | grep "nexusPassword" || true)
    if [ -z $password_key ]; then
        debug "Writing nexusPassword to $properties."
        echo "nexusPassword=$NEXUS_PASSWORD" >> $properties
    fi
}

java_run_test() {
    set_nexus_repo_props
    run ./gradlew -i -b $file test
}

java_package(){
    set_nexus_repo_props
    run ./gradlew -i -b $file build jar
    file=$(ls build/libs | grep ".*\-$version")
    artifactName=${file/.jar/}
    src="build/libs/$artifactName.jar"
}

java_deploy(){
    set_nexus_repo_props
    run ./gradlew -i -b $file publish
}

java_write_new_version(){
    old_version=${1:? 'Old version is required.'}
    new_version=${2:? 'New version is required.'}
    run sed -i "/^version/s/$old_version/$new_version/" $file
}