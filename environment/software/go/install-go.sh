#!/usr/bin/env -S bash -e

if [ "$EUID" -ne 0 ]; then
  echo "This script must be executed with sudo."
  exec sudo "$0" "$@"
fi

GOVERSION=1.22.4
GOOS=linux
GOARCH=amd64

TMPDIR=$(mktemp -d)

GOTARGZ="go$GOVERSION.$GOOS-$GOARCH.tar.gz"

cleanup() {
  rm -rf "$TMPDIR"
}

trap cleanup EXIT

pushd "$TMPDIR"

wget "https://go.dev/dl/$GOTARGZ"
tar -xvf "$GOTARGZ"

SHORTVERSION=$(echo "$GOVERSION" | cut -d'.' -f1,2)
mv go "go-$SHORTVERSION"

TARGET_DIR="/usr/local/go-$SHORTVERSION"

if [ -d "$TARGET_DIR" ]; then
  read -p "$TARGET_DIR already exists. Overwrite? [y/n] " -n 1 -r answer

  if [[ $answer =~ ^[Yy]$ ]]; then
    rm -rf "$TARGET_DIR"
    mv "go-$SHORTVERSION" /usr/local
    echo "Replaced $TARGET_DIR with the new Go version ($GOVERSION)."
  else
    echo -e "\nAborted."
    exit 1
  fi
else
  mv "go-$SHORTVERSION" /usr/local
  echo "Installed Go $GOVERSION to $TARGET_DIR."
fi

popd