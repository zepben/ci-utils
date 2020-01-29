# Commands

See _init.sh_ for commands.

# Env vars 

[pipeline env vars](../README.md)

[Java env vars](../Java/README.md)

[CSharp env vars](../CSharp/README.md)

[Python env vars](../Python/README.md)

# Running Docker locally
docker run -it --env-file D:\Projects\vm-container-images\pipelines\env.list --mount type=bind,source="D:\Projects\cimproto",target="/app" --rm --entrypoint bash zepben/pipeline-all