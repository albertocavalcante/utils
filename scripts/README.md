# Scripts

This directory contains utility scripts for various tasks.

## Available Scripts

### github_tag_filter.py

A utility script to fetch and filter tags from any GitHub repository. It allows
filtering tags by version patterns and displays results in a formatted table.

To run using uv:

```bash
# Basic usage
uv run github_tag_filter.py owner/repo

# Examples:
uv run github_tag_filter.py bazelbuild/bazel
uv run github_tag_filter.py tensorflow/tensorflow -f "2.*"

# Filter options:
# - "X.*" : Match major version X
# - ">X.Y.Z" : Greater than version X.Y.Z
# - "<X.Y.Z" : Less than version X.Y.Z
# - ">=X.Y.Z" : Greater than or equal to version X.Y.Z
# - "<=X.Y.Z" : Less than or equal to version X.Y.Z
# - "X.Y.Z-A.B.C" : Range between X.Y.Z and A.B.C (inclusive)

# Apply multiple filters
uv run github_tag_filter.py bazelbuild/bazel -f "5.*" -f ">5.4.1"

# Hide URLs in output
uv run github_tag_filter.py bazelbuild/bazel --no-urls

# Show tarball URLs instead of release URLs
uv run github_tag_filter.py bazelbuild/bazel --tarball
```

By default, the script shows GitHub release URLs. Use the `--no-urls` flag to
hide URLs completely, or the `--tarball` flag to show tarball URLs instead of
release URLs.
