# Bazel

## Info

```sh
bazel info output_base
```

## Bzlmod

```sh
bazel mod graph
```

```sh
bazel mod graph --verbose
```

```sh
bazel mod show_repo bazel_skylib
```

## Query

```sh
bazel query @local_config_cc//:toolchain --output=build
```

## Reference

- [Bzlmod and Bazel 8](https://www.youtube.com/live/jBadmXmheOQ?si=R7Ef2AWF-0of9m77)
