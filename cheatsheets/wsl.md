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

## Reference

- [How to Shrink a WSL2 Virtual Disk](https://stephenreescarter.net/how-to-shrink-a-wsl2-virtual-disk/)
- [Automatic Backups for WSL2](https://stephenreescarter.net/automatic-backups-for-wsl2/)
