#!/usr/bin/env bash

GOVERSION=1.22.0
GOOS=linux
GOARCH=amd64

TMPDIR=$(mktemp -d)

GOTARGZ=go$GOVERSION.$GOOS-$GOARCH.tar.gz

pushd $TMPDIR

wget https://go.dev/dl/$GOTARGZ
tar -xvf $GOTARGZ

SHORTVERSION=$(echo $GOVERSION | cut -d'.' -f1,2)
mv go go-$SHORTVERSION
sudo mv go-$SHORTVERSION /usr/local

popd



