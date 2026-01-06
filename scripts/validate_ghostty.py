#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///

import subprocess
import sys
import os
import shutil

# Configuration
DEFAULT_CONFIG_PATH = "dotfiles/ghostty/.config/ghostty/config"
MACOS_GHOSTTY_PATH = "/Applications/Ghostty.app/Contents/MacOS/ghostty"

def get_ghostty_command() -> str:
    """
    Locates the ghostty executable.
    Prioritizes PATH, then falls back to the standard macOS application path.
    """
    # 1. Try finding it in PATH
    ghostty_in_path = shutil.which("ghostty")
    if ghostty_in_path:
        return ghostty_in_path
    
    # 2. Check standard macOS location
    if os.path.exists(MACOS_GHOSTTY_PATH):
        return MACOS_GHOSTTY_PATH
        
    return None

def validate_config(config_path: str) -> bool:
    """
    Validates the Ghostty configuration file.
    """
    ghostty_cmd = get_ghostty_command()
    if not ghostty_cmd:
        print("❌ Error: 'ghostty' executable not found in PATH or standard locations.")
        return False

    abs_config_path = os.path.abspath(config_path)
    if not os.path.exists(abs_config_path):
        print(f"❌ Error: Config file not found at: {abs_config_path}")
        return False

    print(f"🔍 Validating Ghostty config: {config_path}")
    print(f"   Using executable: {ghostty_cmd}")

    try:
        # Run validation directly, inheriting environment and standard IO
        # This mimics the behavior of a simple shell script which we know works
        result = subprocess.run(
            [ghostty_cmd, "+validate-config", "--config-file", config_path]
        )

        if result.returncode == 0:
            print("✅ Configuration is valid!")
            return True
        else:
            print(f"❌ Configuration is invalid (Exit Code: {result.returncode})")
            return False

    except Exception as e:
        print(f"❌ Unexpected error during validation: {e}")
        return False

def main():
    # Determine config path from args or default
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = DEFAULT_CONFIG_PATH

    success = validate_config(config_path)
    
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()