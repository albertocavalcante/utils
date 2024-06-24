#!/usr/bin/env -S bash -ex

urls=(
    "github.com/spf13/cobra-cli@latest"
    "github.com/bazelbuild/buildtools/buildozer@latest"    
    "github.com/bazelbuild/buildtools/buildifier@latest"
)

for url in "${urls[@]}"; do
    go install "$url"
done
