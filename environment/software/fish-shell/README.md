# Fish Shell

## Installation

- [Installation](https://fishshell.com/docs/current/index.html#id1)

### Ubuntu

```sh
sudo apt-add-repository ppa:fish-shell/release-3
sudo apt update
sudo apt install fish
```

**Source:** _https://launchpad.net/~fish-shell/+archive/ubuntu/release-3_

## Configuration

### Edit

```sh
vim ~/.config/fish/config.fish
```

### Variables

```sh
vim ~/.config/fish/fish_variables
```

## Configuration Template

- [config.fish.sh](./config.fish.sh)

### Utilities

#### `fish_remove_path`

```sh
fish_remove_path /opt/gradle/gradle-7.6/bin
```

**Source:**
_https://github.com/fish-shell/fish-shell/issues/8604#issuecomment-1169638533_

## StackOverflow Questions

- [Cannot understand command substitution in Fish Shell](https://stackoverflow.com/questions/3281220/cannot-understand-command-substitution-in-fish-shell)
