#!/bin/bash
set -e

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BREWFILE="$SCRIPT_DIR/Brewfile"
IGNOREFILE="$SCRIPT_DIR/.brewignore"

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Ensure Homebrew is installed
check_brew() {
    if ! command -v brew &> /dev/null; then
        log_error "Homebrew is not installed. Please run bootstrap.sh first."
        exit 1
    fi
}

# --- Command: Apply (Code -> System) ---
cmd_apply() {
    log_info "Applying state from Brewfile..."
    
    # Install dependencies from Brewfile
    # --no-lock to prevent it from overwriting the lockfile with 'current' versions 
    # if we strictly want to trust the lockfile we should use it, but for now 
    # we trust the Brewfile manifest and let brew resolve latest compatible.
    brew bundle install --file="$BREWFILE" --verbose

    log_info "State applied successfully."
}

# --- Command: Check/Audit (Reconciliation) ---
cmd_audit() {
    log_info "Auditing system state..."

    # 1. Get list of installed leaves (packages that are not dependencies of others)
    INSTALLED_LEAVES=$(brew leaves)
    INSTALLED_CASKS=$(brew list --cask)
    
    DRIFT_FOUND=false

    echo "--- Unmanaged Packages (Installed but not in Brewfile) ---"
    
    # Process both lists
    for pkg in $INSTALLED_LEAVES $INSTALLED_CASKS; do
        if [ -z "$pkg" ]; then continue; fi

        # Check if present in Brewfile (exact match in quotes)
        if ! grep -q "\"$pkg\"" "$BREWFILE"; then
            # Check if ignored
            if [ -f "$IGNOREFILE" ] && grep -qE "^$pkg$" "$IGNOREFILE"; then
                echo -e "${YELLOW}IGNORED:${NC} $pkg"
            else
                echo -e "${RED}DRIFT:${NC}   $pkg"
                DRIFT_FOUND=true
            fi
        fi
    done

    if [ "$DRIFT_FOUND" = true ]; then
        echo ""
        log_warn "Drift detected. These packages are installed but not tracked."
        log_warn "Run './brew-manager.sh capture' to add them to Brewfile."
        log_warn "Run 'brew uninstall <pkg>' to remove them."
        log_warn "Add them to .brewignore to keep them local-only."
    else
        log_info "System is in sync with Brewfile (plus ignored items)."
    fi
}

# --- Command: Capture (System -> Code) ---
cmd_capture() {
    log_info "Capturing current system state to Brewfile..."

    TEMP_BREWFILE="$SCRIPT_DIR/Brewfile.tmp"
    FINAL_BREWFILE="$BREWFILE"
    
    # Dump current state to temp file
    # --describe adds comments about what the package is. We will keep these.
    brew bundle dump --file="$TEMP_BREWFILE" --force --describe

    log_info "Processing versions and filtering..."
    
    # Create a clean temporary file for the result
    > "$BREWFILE.new"

    while IFS= read -r line; do
        # 1. Check for Ignore List
        if [[ "$line" =~ (brew|cask)[[:space:]]+\"([^\"]+)\" ]]; then
            PKG_NAME="${BASH_REMATCH[2]}"
            TYPE="${BASH_REMATCH[1]}"
            
            # Check if this package is in the ignore list
            if [ -f "$IGNOREFILE" ] && grep -qE "^$PKG_NAME$" "$IGNOREFILE"; then
                echo "Skipping ignored package: $PKG_NAME"
                continue
            fi

            # 2. Fetch Version Information
            VERSION=""
            if [ "$TYPE" == "brew" ]; then
                # Get formula version (first line of info, usually "stable x.y.z")
                # We use 'brew info --json' for reliability or text parsing. 
                # Text parsing is faster for single items.
                VERSION=$(brew info --json=v2 "$PKG_NAME" | jq -r '.formulae[0].versions.stable // .formulae[0].versions.head')
            elif [ "$TYPE" == "cask" ]; then
                VERSION=$(brew info --cask --json=v2 "$PKG_NAME" | jq -r '.casks[0].version')
            fi

            # Append version as comment if found
            if [ -n "$VERSION" ] && [ "$VERSION" != "null" ]; then
                # Check if line already has a comment (from --describe)
                if [[ "$line" == *#* ]]; then
                    echo "$line (v$VERSION)" >> "$BREWFILE.new"
                else
                    echo "$line # v$VERSION" >> "$BREWFILE.new"
                fi
            else
                echo "$line" >> "$BREWFILE.new"
            fi
        else
            # Pass through other lines (taps, comments, etc.)
            echo "$line" >> "$BREWFILE.new"
        fi
    done < "$TEMP_BREWFILE"
    
    # Move new file to actual Brewfile
    mv "$BREWFILE.new" "$BREWFILE"
    rm "$TEMP_BREWFILE"

    log_info "Brewfile updated with versions successfully."
}

# --- Main ---
check_brew

case "$1" in
    apply)
        cmd_apply
        ;;
    audit)
        cmd_audit
        ;;
    capture)
        cmd_capture
        ;;
    *)
        echo "Usage: $0 {apply|audit|capture}"
        echo "  apply   : Install packages from Brewfile."
        echo "  audit   : Check for packages installed but not in Brewfile."
        echo "  capture : Update Brewfile with currently installed packages (respecting .brewignore)."
        exit 1
        ;;
esac
