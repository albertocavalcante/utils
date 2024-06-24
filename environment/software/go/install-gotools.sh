#!/usr/bin/env -S bash -ex

urls=(
    "golang.org/x/tools/gopls@latest"
    "golang.org/dl/gotip@latest"

    "github.com/go-delve/delve/cmd/dlv@latest"

    "honnef.co/go/tools/cmd/staticcheck@latest"

    "github.com/spf13/cobra-cli@latest"

    "github.com/bazelbuild/buildtools/buildozer@latest"    
    "github.com/bazelbuild/buildtools/buildifier@latest"
)

for url in "${urls[@]}"; do
    go install "$url"
done
