#!/bin/bash

mkdir -p /scripts
rm -rf /etc/localtime
ln -s /usr/share/zoneinfo/Australia/Sydney /etc/localtime

# This supposed to be unnecessary, but there might be old things java that need it
# TODO: probably remove when moved over to newer Java (>11)
echo "Australia/Sydney" > /etc/timezone
