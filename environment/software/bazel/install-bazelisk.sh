#!/usr/bin/env bash

#
# Source: https://stackoverflow.com/a/67538831/12249394
#

export BAZELISK_VERSION=1.18.0

wget "https://github.com/bazelbuild/bazelisk/releases/download/v$BAZELISK_VERSION/bazelisk-linux-amd64"
chmod +x bazelisk-linux-amd64
mv bazelisk-linux-amd64 /usr/local/bin/bazel

echo Installation of 'bazelisk' is complete. Feel free to launch it using 'bazel'
