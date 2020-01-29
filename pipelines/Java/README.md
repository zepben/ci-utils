# Commands

See _init.sh_ for commands.

# Env vars - addition to [pipeline env vars](../README.md)

NEXUS_USERNAME

NEXUS_PASSWORD

NEXUS_MAVEN_REPO

NEXUS_MAVEN_RELEASE

NEXUS_MAVEN_SNAPSHOT

# Running Docker locally

docker run -it --env-file D:\Projects\vm-container-images\pipelines\env.list --mount type=bind,source="D:\Projects\cimcap",target="/app" --rm --entrypoint bash zepben/pipeline-java-openjdk:slim