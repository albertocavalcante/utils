# Go

## About

`install-go.sh` is a utility bash script that install Go on Linux. It has been tested only on WSL2 Ubuntu.

It will add a new folder at `/usr/local`, containing the Go release version specified (e.g. `/usr/local/go1.22`).

After installing it, you need to update your `PATH` accordingly.

### fish-shell

Update `config.fish` using Vim

```sh
vim ~/.config/fish/config.fish
:s/go-1.21/go-1.22/
:wq
```

Reload Fish Shell

```sh
source ~/.config/fish/config.fish
```

On my `config.fish` I have the following lines to set both `GOROOT` and add it to the `PATH`:

```sh
export GOROOT=/usr/local/go-1.22

fish_add_path $GOROOT/bin
```

I also set `GOPATH` and `GOBIN`:

```sh
export GOPATH=$HOME/projects/go
export GOBIN=$GOPATH/bin

fish_add_path $GOPATH/bin
```
