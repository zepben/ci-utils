#!/bin/bash

mkdir -p scripts
rm -rf /etc/localtime
ln -s /usr/share/zoneinfo/Australia/Sydney /etc/localtime