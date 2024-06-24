#!/usr/bin/env bash

if [ "$EUID" -ne 0 ]; then
  echo "This script must be executed with sudo."
  exec sudo "$0" "$@"
fi

GOVERSION=1.22.4
GOOS=linux
GOARCH=amd64

TMPDIR=$(mktemp -d)

GOTARGZ=go$GOVERSION.$GOOS-$GOARCH.tar.gz

cleanup() {
  rm -rf $TMPDIR
}

trap cleanup EXIT

pushd $TMPDIR

wget https://go.dev/dl/$GOTARGZ
tar -xvf $GOTARGZ

SHORTVERSION=$(echo $GOVERSION | cut -d'.' -f1,2)
mv go go-$SHORTVERSION
sudo mv go-$SHORTVERSION /usr/local

popd
