@echo off
rem check-msvc.bat - list Visual Studio / Build Tools, MSVC toolsets, MSBuild and
rem Windows SDKs installed on this machine. Read-only; installs nothing.
rem Needs vswhere.exe (ships with the Visual Studio Installer) for VS 2017+.
setlocal EnableExtensions EnableDelayedExpansion

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :novswhere

echo ===== Visual Studio / Build Tools instances (vswhere, incl. incomplete + Preview) =====
"%VSWHERE%" -all -products * -prerelease

echo.
echo ===== Per-instance MSVC toolsets and MSBuild =====
for /f "usebackq delims=" %%I in (`"%VSWHERE%" -all -products * -prerelease -property installationPath`) do call :report "%%I"
goto :common

:report
echo.
echo --- %~1
if not exist "%~1\MSBuild\Current\Bin\MSBuild.exe" goto :nomsb
for /f "delims=" %%V in ('"%~1\MSBuild\Current\Bin\MSBuild.exe" -version -nologo') do echo   MSBuild         : %%V
goto :msbdone
:nomsb
echo   MSBuild         : not installed
:msbdone
if not exist "%~1\VC\Tools\MSVC\" goto :nomsvc
set "DEF="
if exist "%~1\VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt" set /p DEF=<"%~1\VC\Auxiliary\Build\Microsoft.VCToolsVersion.default.txt"
echo   Default toolset : !DEF!
for /d %%T in ("%~1\VC\Tools\MSVC\*") do echo   Toolset         : %%~nxT
goto :eof
:nomsvc
echo   MSVC            : NOT INSTALLED - add the "C++ build tools" workload
goto :eof

:novswhere
echo vswhere.exe not found at "%VSWHERE%".
echo No Visual Studio 2017+ / Build Tools installed, or the VS Installer is missing.

:common
echo.
echo ===== Windows 10/11 SDKs =====
dir /b /ad "%ProgramFiles(x86)%\Windows Kits\10\Include" 2>nul || echo none found

echo.
echo ===== cl.exe / msbuild.exe on PATH in THIS shell =====
where cl >nul 2>&1
if errorlevel 1 goto :nocl
where cl
rem cl prints its banner (compiler version) to stderr and exits non-zero without args.
cl 2>&1 | findstr /i /c:"Version"
goto :msb
:nocl
echo cl.exe not on PATH - open "x64 Native Tools Command Prompt" for VS to get it.
:msb
where msbuild 2>nul || echo msbuild.exe not on PATH

endlocal
