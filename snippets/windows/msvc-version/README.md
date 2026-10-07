# Which MSVC is installed on this Windows machine?

Two equivalent read-only scripts. Pick one:

```bat
check-msvc.bat
```

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check-msvc.ps1      # human report
powershell -NoProfile -ExecutionPolicy Bypass -File .\check-msvc.ps1 -Json # for tooling
```

Both use `vswhere.exe` (installed with the Visual Studio Installer at
`%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\`), then read the install
tree.

## Reading the output

- **MSBuild version is not the MSVC version.** A pin such as
  `msft-msbuild-2022-17-10-6` means VS/Build Tools 2022 **17.10.6**, which ships
  MSBuild 17.10.x. The compiler is a separate component, so check the toolset
  list.
- VS 2022 17.10 pairs with the **v143** platform toolset, **MSVC 14.40.x**,
  `_MSC_VER` 1940.
- `_MSC_VER` = 1900 + toolset minor (14.40 -> 1940, 14.38 -> 1938, 14.29 ->
  1929).
- `cl.exe` reports `19.<minor>.<build>`; the leading 19 is the compiler major,
  not the VS year.
- "MSVC: NOT INSTALLED" means the instance has no `VC\Tools\MSVC`. A Build Tools
  install with only the MSBuild workload has no `cl.exe`. It needs
  `Microsoft.VisualStudio.Workload.VCTools`.
- Several toolsets can sit side by side. The _default_ one is in
  `VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt`; a build can pick
  another with `-vcvars_ver=14.38` or `/p:VCToolsVersion=...`.

## One-liners

```powershell
# every instance with the C++ tools component
& "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe" -all -products * -prerelease `
  -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath

# compiler banner from a Developer Prompt
cl
```

```bat
rem VS 2015 and older are not covered by default; add -legacy to vswhere to list them.
```

Limits: VS 2015 and older (use `vswhere -legacy`) and non-VS toolchains
(clang-cl, MinGW) are not reported.
