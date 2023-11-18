#!/usr/bin/env bash

[ "$EUID" -eq 0 ] || exec sudo "$0" "$@"
export GRADLE_VERSION=8.4
export GRADLE_DISTRIBUTION=all
export GRADLE_ARTIFACT="gradle-${GRADLE_VERSION}"
export GRADLE_ZIP="${GRADLE_ARTIFACT}-${GRADLE_DISTRIBUTION}.zip"
export GRADLE_DISTRIBUTION_URL="https://services.gradle.org/distributions/${GRADLE_ZIP}"

export GRADLE_HOME_DIR=/opt/gradle

export TMP_DIR="$(mktemp -d -t gradle.XXXXXX)"
export GRADLE_ZIP_DOWNLOAD_LOCATION="${TMP_DIR}/${GRADLE_ZIP}"

[ -d "$GRADLE_HOME_DIR" ] || mkdir -p "$GRADLE_HOME_DIR"

wget "$GRADLE_DISTRIBUTION_URL" -O "$GRADLE_ZIP_DOWNLOAD_LOCATION"

unzip -d "$GRADLE_HOME_DIR" "$GRADLE_ZIP_DOWNLOAD_LOCATION"

ls -l "${GRADLE_HOME_DIR}/${GRADLE_ARTIFACT}"

# FISH
# fish_add_path /opt/gradle/gradle-8.4/bin
