#!/bin/bash

info "build tool: maven"
debug "NEXUS_USERNAME=$NEXUS_USERNAME"
debug "NEXUS_PASSWORD=$NEXUS_PASSWORD"
debug "NEXUS_MAVEN_REPO=$NEXUS_MAVEN_REPO"
debug "NEXUS_MAVEN_RELEASE=$NEXUS_MAVEN_RELEASE"
debug "NEXUS_MAVEN_SNAPSHOT=$NEXUS_MAVEN_SNAPSHOT"

NEXUS_USERNAME=${NEXUS_USERNAME:?'Maven repo username variable missing.'}
NEXUS_PASSWORD=${NEXUS_PASSWORD:?'Maven repo password variable missing.'}
NEXUS_MAVEN_REPO=${NEXUS_MAVEN_REPO:?'Maven repo url variable missing.'}
NEXUS_MAVEN_RELEASE=${NEXUS_MAVEN_RELEASE:?'Maven release url variable missing.'}
NEXUS_MAVEN_SNAPSHOT=${NEXUS_MAVEN_SNAPSHOT:?'Maven snapshot url variable missing.'}

if [[ "$file" != *".xml" ]]; then
    fail "File $file needs to be xml."
fi

version=$(xmlstarlet pyx $file | grep -v ^A | xmlstarlet p2x | xmlstarlet sel -t -v "/project/version")

java_run_test() {
    run mvn clean test -f $file -s /usr/share/maven/conf/settings.xml -Dserver.username=$NEXUS_USERNAME -Dserver.password=$NEXUS_PASSWORD -Dserver.repo.url=$NEXUS_MAVEN_REPO
}

java_package(){
    run mvn clean package -f $file -s /usr/share/maven/conf/settings.xml -Dserver.username=$NEXUS_USERNAME -Dserver.password=$NEXUS_PASSWORD -Dserver.repo.url=$NEXUS_MAVEN_REPO
    artifactId=$(xmlstarlet pyx $file | grep -v ^A | xmlstarlet p2x | xmlstarlet sel -t -v "/project/artifactId")
    artifactName="${artifactId}-${version}"
    src="target/${artifactName}.jar"
}

java_deploy(){
    run mvn clean deploy -f $file -s /usr/share/maven/conf/settings.xml -Dserver.username=$NEXUS_USERNAME -Dserver.password=$NEXUS_PASSWORD -Dserver.repo.url=$NEXUS_MAVEN_REPO -Dserver.release.url=$NEXUS_MAVEN_RELEASE -Dserver.snapshot.url=$NEXUS_MAVEN_SNAPSHOT
}

java_write_new_version(){
    old_version=${1:? 'Old version is required.'}
    new_version=${2:? 'New version is required.'}
    run xmlstarlet ed -P -L -N pom="http://maven.apache.org/POM/4.0.0" -u "/pom:project/pom:version" -v "$new_version" $file
}