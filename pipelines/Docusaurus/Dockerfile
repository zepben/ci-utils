FROM node:24-alpine

RUN apk add --no-cache --update
RUN apk add --no-cache \
 git \
 zip \
 bash \
 make \
 tar \
 jq 

# copy the templates first, as they rarily change
COPY ./node_modules /node_modules
 
RUN mkdir /templates
COPY ./templates /templates

EXPOSE 3000

WORKDIR /docs
