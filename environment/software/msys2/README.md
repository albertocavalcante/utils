# MSYS2

- [MSYS2 Installer Source Code](https://github.com/msys2/msys2-installer)
- [Configuration for 3rd party Terminals, including Windows Terminal](https://www.msys2.org/docs/terminals/)

On my machine using WinGet did not work with the message `Installation space required: "521.74 MB" Temporary space required: "256.00 MB" Local repository size: "0.00 bytes"`. I ended up invoking the `.exe` and installing through the GUI.

## Manual

**Example from WinGet install**

```bat
%TEMP%\WinGet\MSYS2.MSYS2.20240507\msys2-x86_64-20240507.exe install --confirm-command --root C:\msys64
```

**Note:** I invoked without the arguments.
