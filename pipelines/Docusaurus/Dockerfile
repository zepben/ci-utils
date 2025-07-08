FROM node:24-alpine

RUN apk add --no-cache --update
RUN apk add --no-cache \
 git \
 zip \
 bash \
 jq 
 
RUN mkdir /templates
COPY ./templates /templates

WORKDIR /docs
# ENTRYPOINT /templates/build_docs.sh
# ENTRYPOINT /bin/bash
