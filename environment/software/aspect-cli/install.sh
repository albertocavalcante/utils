#!/usr/bin/env -S bash -e

TMPDIR=$(mktemp -d)

cleanup() {
  rm -rf $TMPDIR
}

trap cleanup EXIT

REPO="aspect-build/aspect-cli"

GITHUB_TOKEN=$(gh auth token)

LATEST_VERSION=$(curl -sL \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/$REPO/releases/latest | jq -r '.tag_name')

echo $LATEST_VERSION

wget https://github.com/$REPO/releases/download/$LATEST_VERSION/aspect-linux_amd64 -O $TMPDIR/aspect

sudo cp $TMPDIR/aspect /usr/local/bin/aspect
sudo chmod +x /usr/local/bin/aspect

echo "Installed Aspect CLI $LATEST_VERSION to /usr/local/bin/aspect"
