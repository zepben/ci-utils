FROM node:24-alpine

RUN apk add --no-cache --update
RUN apk add --no-cache \
 git \
 zip \
 bash \
 make \
 tar \
 jq 
 
RUN mkdir /templates
COPY ./templates /templates
COPY ./node_modules /node_modules

EXPOSE 3000

WORKDIR /docs
