# Bazel on Windows

This is a dump of some bugs / errors and troubleshooting I've been doing when executing Bazel on Windows.

## rules_go

command:

```bat
bazel build //...
```

error:

```txt
The target you are compiling requires MSYS gcc / MINGW gcc.
Bazel couldn't find gcc installation on your machine.
Please install MSYS gcc / MINGW gcc and set BAZEL_SH environment variable
```

Then I had to install MinGW, through MSYS2. For reference, check [MinGW](/environment/software/mingw/) and [MSYS2](/environment/software/msys2/).

Once they've been installed I did set:

```bat
set BAZEL_SH=C:\msys64\usr\bin\bash.exe
```

### Additional Resources

- [Bazel: Windows Troubleshooting](https://bazel.build/install/windows#troubleshooting)
