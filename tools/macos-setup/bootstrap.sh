#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== macOS Bootstrap Script ===${NC}"

# 1. Install Xcode Command Line Tools
if type xcode-select >&- && xpath=$( xcode-select --print-path ) && test -d "${xpath}" && test -x "${xpath}" ; then
   echo -e "${GREEN}[OK] Xcode Command Line Tools already installed.${NC}"
else
   echo "Installing Xcode Command Line Tools..."
   xcode-select --install
   # Wait for user to finish installation
   read -p "Press [Enter] after the Xcode installation popup has finished..."
fi

# 2. Install Homebrew
if ! command -v brew &> /dev/null; then
    echo "Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    
    # Setup shell env for Apple Silicon (M1/M2/M3) or Intel
    if [[ $(uname -m) == 'arm64' ]]; then
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"
        eval "$(/opt/homebrew/bin/brew shellenv)"
    else
        echo 'eval "$(/usr/local/bin/brew shellenv)"' >> "$HOME/.zprofile"
        eval "$(/usr/local/bin/brew shellenv)"
    fi
else
    echo -e "${GREEN}[OK] Homebrew already installed.${NC}"
fi

# 3. Hand off to the Manager
echo "Running Brew Manager to apply state..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
chmod +x "$SCRIPT_DIR/brew-manager.sh"
"$SCRIPT_DIR/brew-manager.sh" apply

echo -e "${GREEN}Bootstrap complete!${NC}"
