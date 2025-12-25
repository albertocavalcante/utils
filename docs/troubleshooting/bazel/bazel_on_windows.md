# Bazel on Windows

This is a dump of some bugs / errors and troubleshooting I've been doing when
executing Bazel on Windows.

## rules_go

> Some the issues below would have been avoided if I had read
> [Using rules_go on Windows](https://github.com/bazelbuild/rules_go/blob/master/windows.rst)
> before.

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

Then I had to install MinGW, through MSYS2. For reference, check
[MinGW](/environment/software/mingw/) and [MSYS2](/environment/software/msys2/).

Once they've been installed I did set:

```bat
set BAZEL_SH=C:\msys64\usr\bin\bash.exe
```

It happens that I only had `gcc` installed in

So then I got the error

```sh
c:\msys64\mingw64\bin\gcc -MD -MF bazel-out/x64_windows-fastbuild/bin/tests/core/cgo/_objs/split_import_c/split_import_c.d -frandom-seed=bazel-out/x64_windows-fastbuild/bin/tests/core/cgo/_objs/split_import_c/split_import_c.o -iquote . -iquote bazel-out/x64_windows-fastbuild/bin -c tests/core/cgo/split_import_c.c -o bazel-out/x64_windows-fastbuild/bin/tests/core/cgo/_objs/split_import_c/split_import_c.o
# Configuration: 8e385259d0f73030678319c9d586ecc5f0a2d5765e7355387b2c043b249cc0e0
# Execution platform: //go/toolchain:windows_amd64_cgo
Action failed to execute: java.io.IOException: ERROR: src/main/native/windows/process.cc(202): CreateProcessW("c:\msys64\mingw64\bin\gcc" -MD -MF bazel-out/x64_windows-fastbuild/bin/tests/core/cgo/_objs/split_import_c/split_import_c.d -frandom-seed=bazel-out/x64_windows-fastbuild/bin/tests/core/cgo/_objs/split_import_c/split_import_c.o -iquote . -iquote bazel-out/x64_windows-fastbuild/bin -c tests/core/cgo/split_import_c.c -o bazel-out/x64_windows-fastbuild/bin/tests/core/cgo/_objs/split_import_c/split_import_c.o): O sistema não pode encontrar o arquivo especificado.
```

It attempted to use `gcc` ìn the `C:\msys64\mingw\bin` directory. Nowadays
`MSYS2` advises to install the `ucrt` flavor of `MinGW`, but it ends up having
gcc only at `C:\msys64\ucrt64\bin` and not in `C:\msys64\mingw64\bin`

In order to install the `mingw` flavor I executed:

```sh
pacman -S mingw-w64-x86_64-gcc
```

Then I started to get the error:

```sh
tests/legacy/examples/cgo/cc_dependency/cxx_version.cc:1:10: fatal error: dlfcn.h: No such file or directory
    1 | #include <dlfcn.h>
      |          ^~~~~~~~~
compilation terminated.
```

Then I installed the package
[`mingw-w64-x86_64-dlfcn`](https://packages.msys2.org/package/mingw-w64-x86_64-dlfcn).

```sh
pacman -S mingw-w64-x86_64-dlfcn
```

Then I tried `bazel build //...` and got the error:

```sh
c:/msys64/mingw64/bin/../lib/gcc/x86_64-w64-mingw32/13.2.0/../../../../x86_64-w64-mingw32/bin/ld.exe: cannot find -lc_version_so: No such file or directory
collect2.exe: error: ld returned 1 exit status
```

It took me a while until I
[searched for `c_version_go` on GitHub](https://github.com/search?type=code&q=c_version_so)
and found a
[match in the `rules_go` repository](https://github.com/bazelbuild/rules_go/blob/master/.bazelci/presubmit.yml#L259).
Then I realized I had to exclude some targets that wouldn't be possible to
compile on Windows.

I ended up with:

```sh
bazel build --verbose_failures -- "//..." "-@com_github_golang_protobuf//ptypes:go_default_library_gen" "-@com_google_protobuf//:any_proto" "-@com_google_protobuf//:api_proto" "-@com_google_protobuf//:compiler_plugin_proto" "-@com_google_protobuf//:descriptor_proto" "-@com_google_protobuf//:duration_proto" "-@com_google_protobuf//:empty_proto" "-@com_google_protobuf//:field_mask_proto" "-@com_google_protobuf//:protobuf" "-@com_google_protobuf//:protoc" "-@com_google_protobuf//:protoc_lib" "-@com_google_protobuf//:source_context_proto" "-@com_google_protobuf//:struct_proto" "-@com_google_protobuf//:timestamp_proto" "-@com_google_protobuf//:type_proto" "-@com_google_protobuf//:wrappers_proto" "-@gogo_special_proto//github.com/gogo/protobuf/gogoproto:gogoproto" "-//go/tools/bazel:bazel_test" "-@io_bazel_rules_go//proto:gogofaster_proto" "-@io_bazel_rules_go//proto:go_grpc" "-@io_bazel_rules_go//proto:go_proto" "-@io_bazel_rules_go//proto:go_proto_bootstrap" "-@org_golang_x_crypto//ed25519:ed25519_test" "-@org_golang_x_crypto//sha3:sha3_test" "-@org_golang_x_sys//windows/registry:registry_test" "-@org_golang_x_sys//windows/svc/eventlog:eventlog_test" "-@org_golang_x_sys//windows/svc:svc_test" "-@org_golang_x_text//language:language_test" "-//proto:combo_grpc" "-//proto:combo_proto" "-//proto:gofast_grpc" "-//proto:gofast_proto" "-//proto:gogofaster_grpc" "-//proto:gogofaster_proto" "-//proto:gogofast_grpc" "-//proto:gogofast_proto" "-//proto:gogo_grpc" "-//proto:gogo_proto" "-//proto:gogoslick_grpc" "-//proto:gogoslick_proto" "-//proto:gogotypes_grpc" "-//proto:gogotypes_proto" "-//proto:go_grpc" "-//proto:go_proto" "-//proto:go_proto_bootstrap" "-//proto:gostring_grpc" "-//proto:gostring_proto" "-//proto/wkt:any_go_proto" "-//proto/wkt:api_go_proto" "-//proto/wkt:compiler_plugin_go_proto" "-//proto/wkt:descriptor_go_proto" "-//proto/wkt:duration_go_proto" "-//proto/wkt:empty_go_proto" "-//proto/wkt:field_mask_go_proto" "-//proto/wkt:source_context_go_proto" "-//proto/wkt:struct_go_proto" "-//proto/wkt:timestamp_go_proto" "-//proto/wkt:type_go_proto" "-//proto/wkt:wrappers_go_proto" "-//tests:buildifier_test" "-@test_chdir_remote//sub:go_default_test" "-//tests/core/cgo:dylib_client" "-//tests/core/cgo:dylib_test" "-//tests/core/cgo:generated_dylib_client" "-//tests/core/cgo:generated_dylib_test" "-//tests/core/cgo:versioned_dylib_client" "-//tests/core/cgo:versioned_dylib_test" "-//tests/core/cgo:generated_versioned_dylib_client" "-//tests/core/cgo:generated_versioned_dylib_test" "-//tests/core/cross:proto_test" "-//tests/core/go_path:go_path" "-//tests/core/go_path:go_path_test" "-//tests/core/go_path:nodata_path" "-//tests/core/go_path:copy_path" "-//tests/core/go_path:archive_path" "-//tests/core/go_path/pkg/lib:vendored" "-//tests/core/go_path/pkg/lib:go_default_test" "-//tests/core/go_path/pkg/lib:go_default_library" "-//tests/core/go_path/pkg/lib:embed_test" "-//tests/core/go_path/pkg/lib:embed_lib" "-//tests/core/go_path/cmd/bin:cross" "-//tests/core/go_path/cmd/bin:bin" "-//tests/core/go_plugin:go_plugin" "-//tests/core/go_plugin:go_default_test" "-//tests/core/go_plugin:plugin" "-//tests/core/go_plugin_with_proto_library:go_plugin_with_proto_library" "-//tests/core/go_plugin_with_proto_library:go_default_test" "-//tests/core/go_plugin_with_proto_library:plugin" "-//tests/core/go_proto_library:all" "-//tests/core/go_proto_library_importmap:foo_go_proto" "-//tests/core/go_proto_library_importmap:foo_proto" "-//tests/core/go_proto_library_importmap:importmap_test" "-//tests/core/go_test:data_test" "-//tests/core/go_test:pwd_test" "-//tests/core/race:race_test" "-//tests/core/stdlib:buildid_test" "-//tests/examples/executable_name:executable_name" "-//tests/integration/googleapis:color_service" "-//tests/integration/googleapis:color_service_go_proto" "-//tests/integration/googleapis:color_service_proto" "-//tests/integration/googleapis:color_service_test" "-//tests/legacy/examples/cgo/example_command:example_command_test" "-//tests/legacy/examples/cgo/example_command:example_command_script" "-//tests/legacy/examples/cgo/example_command:example_command" "-//tests/legacy/examples/cgo:generate_go_src" "-//tests/legacy/examples/cgo:cgo_lib_test" "-//tests/legacy/examples/cgo:go_default_library" "-//tests/legacy/examples/cgo/cc_dependency:version" "-//tests/legacy/examples/cgo/cc_dependency:c_version_so" "-//tests/legacy/examples/cgo:sub" "-//tests/legacy/examples/proto/dep:useful_go_proto" "-//tests/legacy/examples/proto/dep:useful_proto" "-//tests/legacy/examples/proto/embed:embed_go_proto" "-//tests/legacy/examples/proto/embed:embed_proto" "-//tests/legacy/examples/proto/embed:go_default_library" "-//tests/legacy/examples/proto:go_default_library" "-//tests/legacy/examples/proto/gogo:gogo_test" "-//tests/legacy/examples/proto/gogo:values_go_proto" "-//tests/legacy/examples/proto/gogo:values_proto" "-//tests/legacy/examples/proto/gostyle:gostyle_go_proto" "-//tests/legacy/examples/proto/gostyle:gostyle_proto" "-//tests/legacy/examples/proto/grpc:my_svc_go_proto" "-//tests/legacy/examples/proto/grpc:my_svc_proto" "-//tests/legacy/examples/proto/grpc:not_grpc" "-//tests/legacy/examples/proto/grpc:test_grpc" "-//tests/legacy/examples/proto/lib:lib_go_proto" "-//tests/legacy/examples/proto/lib:lib_proto" "-//tests/legacy/examples/proto:proto_pure_test" "-//tests/legacy/examples/proto:proto_test" "-//tests/legacy/extldflags_rpath:extldflags_rpath_test" "-//tests/legacy/info:info" "-//tests/legacy/proto_ignore_go_package_option:a_go_proto" "-//tests/legacy/proto_ignore_go_package_option:a_proto" "-//tests/legacy/proto_ignore_go_package_option:b_go_proto" "-//tests/legacy/proto_ignore_go_package_option:b_proto" "-//tests/legacy/test_chdir:go_default_test" "-//tests/legacy/test_rundir:go_default_test" "-//tests/legacy/transitive_data:go_default_test" "-//tests/core/cross:darwin_go_cross_cgo" "-//tests/core/cross:linux_go_cross_cgo" "-//tests/core/cross:windows_go_cross_cgo"
```

Still, I got the error:

```sh
ERROR: C:/dev/workspace/rules_go/tests/core/go_test/BUILD.bazel:74:8: output 'tests/core/go_test/only_testmain_test_/only_testmain_test.exe' was not created
ERROR: C:/dev/workspace/rules_go/tests/core/go_test/BUILD.bazel:74:8: GoLink tests/core/go_test/only_testmain_test_/only_testmain_test.exe failed: not all outputs were created or valid
```

I tried to run the target individually to isolate the error and got the same
output:

```sh
bazel build //tests/core/go_test:only_testmain_test --verbose_failures
INFO: Analyzed target //tests/core/go_test:only_testmain_test (0 packages loaded, 0 targets configured).
ERROR: C:/dev/workspace/rules_go/tests/core/go_test/BUILD.bazel:74:8: output 'tests/core/go_test/only_testmain_test_/only_testmain_test.exe' was not created
ERROR: C:/dev/workspace/rules_go/tests/core/go_test/BUILD.bazel:74:8: GoLink tests/core/go_test/only_testmain_test_/only_testmain_test.exe failed: not all outputs were created or valid
Target //tests/core/go_test:only_testmain_test failed to build
INFO: Elapsed time: 1.577s, Critical Path: 0.50s
INFO: 2 processes: 1 internal, 1 local.
ERROR: Build did NOT complete successfully
```

Then... every time I executed this action, a Windows Security pop up appeared
informing it had blocked a suspicius file. I had to manually allow this file and
built again. Then it succeeded.

### Additional Resources

- [Bazel: Windows Troubleshooting](https://bazel.build/install/windows#troubleshooting)

## Reference

### GitHub Issues

- [Setting up VC environment variables failed (WINDOWSSDKDIR) - bazel 4.0.0](https://github.com/bazelbuild/bazel/issues/13261)
