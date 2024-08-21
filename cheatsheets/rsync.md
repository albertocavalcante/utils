# rsync

```sh
rsync --archive --verbose --delete --exclude={'.git/*','.venv/*','node_modules','bazel-*','bazel-bin','bazel-examples','bazel-out','bazel-testlogs','.antlr','build/kotlin/*','target/*','.cache/*','.local/*','.kube/cache/*','.config/*','.rustup/*','.docker/*','.cargo/*','.java/*','.pyenv/*','.dotnet/*','.asdf/*','.amplify/*','.gnupg/*','.astro/*','aws/*','.aws','.azure','go/*','__pycache__/*','.poetry/*','.gradle/*','.m2/*','.npm/*','.nvm/*','.tmux/*','.bazelisk/*','.vscode-server/*','.vscode-server-insiders/*','.vscode-remote-containers/*','esp/*','.espressif/*','.modular/*','github/*','sdk/gotip/*'} $HOME /mnt/c/Users/<username>/wsl2-backup/
```

## Reference

- [How to exclude the multiple directory in rsync?](https://askubuntu.com/questions/1420321/how-to-exclude-the-multiple-directory-in-rsync)
