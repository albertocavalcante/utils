# Windows Subsystem for Linux (WSL)

## WSL CLI

```sh
wsl --list
```

## PowerShell Utils

### Locate `.vhdx` path of a distro

```powershell
(Get-ChildItem -Path HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss | Where-Object { $_.GetValue("DistributionName") -eq 'Ubuntu' }).GetValue("BasePath") + "\ext4.vhdx"
```

**Source:** [How to locate the .vhdx file and disk path for your Linux distribution](https://learn.microsoft.com/en-us/windows/wsl/disk-space#how-to-locate-the-vhdx-file-and-disk-path-for-your-linux-distribution)
