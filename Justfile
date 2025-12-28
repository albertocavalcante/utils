# Justfile - Command Center for 2026 Setup

# Sync everything: updates homebrew, node, and captures state to git
sync:
    topgrade
    @./dotfiles/scripts/brew/brew-manager.sh capture
    @./dotfiles/scripts/pnpm/pnpm-manager.sh capture
    @echo "✅ System state captured. Ready to commit."

# Refresh the dashboard manually
refresh:
    rm -f ~/.cache/motd_github*
    motd

# Fix all formatting issues (Lua, Python, Markdown)
fix:
    @echo "🎨 Fixing formatting..."
    @dprint fmt
    @stylua .
    @if command -v ruff >/dev/null; then ruff format .; fi
    @echo "✅ Formatting complete."

# Install/Restore all links
stow:
    cd dotfiles && ./install.sh

# Open your main TODO list
todo:
    nvim ~/TODO.md

# Quick backup of Raycast
backup-raycast:
    backup-raycast
