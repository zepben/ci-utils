# Commands

See _install-dependencies.sh_ for commands.

# Env vars - addition to [pipeline env vars](../README.md)

ZEPBEN_NUGET_FEED

ZEPBEN_NUGET_FEED_USERNAME

ZEPBEN_NUGET_FEED_PASSWORD

ZEPBEN_NUGET_UPLOAD_FEED

ZEPBEN_NUGET_UPLOAD_KEY

# Running Docker locally

docker run -it --env-file D:\Projects\containers-and-vms\pipelines\CSharp\env.list --mount type=bind,source="D:\Projects\cimproto",target="/app" --rm --entrypoint 
bash mavenrepo.zepben.com:8083/repository/zepben-docker/pipeline-dotnet:latest