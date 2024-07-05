# cmdrc.cmd

## Setup

```bat
copy cmdrc.cmd %USERPROFILE%\cmdrc.cmd
```

```bat
reg add "HKEY_CURRENT_USER\Software\Microsoft\Command Processor" /v AutoRun /t REG_SZ /d "%USERPROFILE%\cmdrc.cmd" /f
```

```bat
notepad %USERPROFILE%\cmdrc.cmd
```

## Reference

- [Is there windows equivalent to the .bashrc file in linux?](https://superuser.com/questions/144347/is-there-windows-equivalent-to-the-bashrc-file-in-linux)
