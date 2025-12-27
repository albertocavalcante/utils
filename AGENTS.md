# Agent Instructions

## Overview

This repository serves as a central hub for development utilities, scripts, and
documentation. System-level environment configurations are externalized in the
`dotfiles` submodule.

## Core Rules

- **Security First**: Security is Priority #1. Always question whether a file,
  config, or secret belongs in the public `dotfiles` or the `dotfiles-private`
  submodule before proceeding.
- **Protocol Inheritance**: Always consult `dotfiles/private/AGENTS.md` for
  extended operational protocols regarding compliance and data handling.
- **Environment Config**: All terminal, shell, and editor configurations must be
  modified within the `dotfiles/` submodule. Do not create or edit local
  configuration files in the root of this repository.- **Submodule Sync**: After
  making changes within `dotfiles/`, ensure the submodule pointer in this
  repository is updated and committed to maintain parity.
- **Stow Update**: After modifying configuration files in `dotfiles/` (e.g.,
  .zshrc, .config/...), run `cd dotfiles && stow -R <package_name>` to refresh
  symlinks (e.g., `stow -R zsh`).
- **Scripts**: Utility scripts in `scripts/` or `tools/` should remain modular
  and not depend on hardcoded local paths where possible.

## Canonical Reference

For system setup, Homebrew packages, and shell aliases, refer to the `dotfiles/`
repository instructions.

## Development

Refer to [CONTRIBUTING.md](./CONTRIBUTING.md) for environment setup, git hooks,
and linting rules.

## Agent Slash Commands

### `/brew-refresh`

Triggers the **Update Brewfile** workflow.

- **Source of Truth**: The detailed steps are defined in
  `.gemini/commands/brew-refresh.toml`.
- **Usage**: Invoke this command to capture the current system state, update the
  `Brewfile`, and commit changes to the `dotfiles` submodule.
