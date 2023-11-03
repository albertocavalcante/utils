#!/usr/bin/env bash

GOVERSION=1.21.3
GOOS=linux
GOARCH=amd64

TMPDIR=$(mktemp -d)

GOTARGZ=go$GOVERSION.$GOOS-$GOARCH.tar.gz

pushd $TMPDIR

wget https://go.dev/dl/$GOTARGZ
tar -xvf $GOTARGZ
mv go go-$VERSION
sudo mv go-$VERSION /usr/local

popd



