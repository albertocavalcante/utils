#!/bin/bash
GHOSTTY="/Applications/Ghostty.app/Contents/MacOS/ghostty"
CONFIG="dotfiles/ghostty/.config/ghostty/config"

"${GHOSTTY}" +validate-config --config-file="${CONFIG}"
