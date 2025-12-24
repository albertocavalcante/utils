# Agent Instructions

## Overview
This repository serves as a central hub for development utilities, scripts, and documentation. System-level environment configurations are externalized in the `dotfiles` submodule.

## Core Rules
- **Environment Config**: All terminal, shell, and editor configurations must be modified within the `dotfiles/` submodule. Do not create or edit local configuration files in the root of this repository.
- **Submodule Sync**: After making changes within `dotfiles/`, ensure the submodule pointer in this repository is updated and committed to maintain parity.
- **Scripts**: Utility scripts in `scripts/` or `tools/` should remain modular and not depend on hardcoded local paths where possible.

## Canonical Reference
For system setup, Homebrew packages, and shell aliases, refer to the `dotfiles/` repository instructions.
