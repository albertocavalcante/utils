<#
.SYNOPSIS
  List every Visual Studio / Build Tools instance, MSVC toolset, MSBuild and
  Windows SDK installed on this machine.

.DESCRIPTION
  Uses vswhere (ships with the VS Installer) to enumerate instances, then reads
  the install tree directly, so it reports MSVC even when MSBuild is the only
  thing a pin like "msbuild-2022-17-10-6" mentions. Nothing is installed or
  modified. Works on Windows PowerShell 5.1 and PowerShell 7.

.PARAMETER Json
  Emit machine-readable JSON instead of the human-readable report.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File .\check-msvc.ps1
  .\check-msvc.ps1 -Json
#>
[CmdletBinding()]
param([switch]$Json)

$ErrorActionPreference = 'Stop'

function Get-FileVer([string]$Path) {
    if (Test-Path $Path) { (Get-Item $Path).VersionInfo.FileVersion } else { $null }
}

# _MSC_VER for the v14x toolset family is 1900 + minor (14.40 -> 1940, 14.29 -> 1929).
function Get-MscVer([string]$Toolset) {
    $v = [version]$Toolset
    if ($v.Major -eq 14) { 1900 + $v.Minor } else { $null }
}

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
$instances = @()
if (Test-Path $vswhere) {
    # -all includes instances with no usable workload; -prerelease includes Preview channels.
    $raw = & $vswhere -all -products * -prerelease -format json
    if ($raw) { $instances = @($raw | ConvertFrom-Json) }
}

$report = foreach ($i in $instances) {
    $root       = $i.installationPath
    $msvcDir    = Join-Path $root 'VC\Tools\MSVC'
    $defaultTxt = Join-Path $root 'VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt'

    $toolsets = @()
    if (Test-Path $msvcDir) {
        $toolsets = @(Get-ChildItem $msvcDir -Directory | Sort-Object { [version]$_.Name } | ForEach-Object {
            $cl = Join-Path $_.FullName 'bin\Hostx64\x64\cl.exe'
            if (-not (Test-Path $cl)) { $cl = Join-Path $_.FullName 'bin\Hostx86\x86\cl.exe' }
            [pscustomobject]@{
                Toolset    = $_.Name
                CompilerCl = Get-FileVer $cl            # e.g. 19.40.33812.0
                MscVer     = Get-MscVer $_.Name         # value of _MSC_VER
            }
        })
    }

    $default = $null
    if (Test-Path $defaultTxt) { $default = (Get-Content $defaultTxt -TotalCount 1).Trim() }

    [pscustomobject]@{
        Name           = $i.displayName
        ProductId      = $i.productId
        Channel        = $i.channelId
        VSVersion      = $i.installationVersion
        Path           = $root
        Complete       = $i.isComplete
        MSBuild        = Get-FileVer (Join-Path $root 'MSBuild\Current\Bin\MSBuild.exe')
        DefaultToolset = $default
        Toolsets       = $toolsets
    }
}

$sdkDir = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\Include'
$sdks = @()
if (Test-Path $sdkDir) {
    $sdks = @(Get-ChildItem $sdkDir -Directory | Where-Object { $_.Name -like '10.*' } |
              Sort-Object { [version]$_.Name } | ForEach-Object Name)
}

# Whatever is first on PATH in *this* shell (only set inside a Developer prompt).
$onPath = [pscustomobject]@{
    cl      = (Get-Command cl.exe      -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
    msbuild = (Get-Command msbuild.exe -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Source)
}

if ($Json) {
    [pscustomobject]@{ Instances = @($report); WindowsSdks = $sdks; OnPath = $onPath } |
        ConvertTo-Json -Depth 6
    return
}

if (-not (Test-Path $vswhere)) {
    Write-Warning "vswhere.exe not found at $vswhere. No Visual Studio 2017+ / Build Tools installed (or the VS Installer is missing)."
}

foreach ($r in $report) {
    Write-Host ""
    Write-Host "=== $($r.Name)  (VS $($r.VSVersion), channel $($r.Channel))" -ForegroundColor Cyan
    Write-Host "  Path            : $($r.Path)"
    Write-Host "  Complete        : $($r.Complete)"
    Write-Host "  MSBuild         : $(if ($r.MSBuild) { $r.MSBuild } else { 'not installed' })"
    if ($r.Toolsets.Count -eq 0) {
        Write-Host "  MSVC            : NOT INSTALLED (no VC\Tools\MSVC; add the 'C++ build tools' workload)" -ForegroundColor Yellow
        continue
    }
    Write-Host "  Default toolset : $($r.DefaultToolset)"
    foreach ($t in $r.Toolsets) {
        Write-Host ("  Toolset {0,-14} cl.exe {1,-14} _MSC_VER {2}" -f $t.Toolset, $t.CompilerCl, $t.MscVer)
    }
}

Write-Host ""
Write-Host "Windows 10/11 SDKs : $(if ($sdks) { $sdks -join ', ' } else { 'none found' })"
Write-Host "cl.exe on PATH     : $(if ($onPath.cl) { $onPath.cl } else { 'not on PATH (open a Developer Prompt to get it)' })"
Write-Host "msbuild.exe on PATH: $(if ($onPath.msbuild) { $onPath.msbuild } else { 'not on PATH' })"
