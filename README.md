This repo is for creating container and virtual machine images using Packer.

#### Tools needed
1. [Packer](https://www.packer.io/downloads.html)
2. [Docker](https://www.docker.com/) (When building docker images)

#### Building Docker image

1. Login to the registry `docker login`.

2. Cd into a directory.

3. Execute `packer build config.json` command.


# Notes

When checking out this repo on **Windows**, the line endings will be _CRLF_. This will be a problem for the sh script files. To avoid that run:

**When checking out commits from 12/05/2020 and later, this should not be a problem after adding .gitattributes file.**

`git config core.eol lf`

`git config core.autocrlf input`