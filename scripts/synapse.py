#!/usr/bin/env -S uv run
# /// script
# dependencies = ["pyyaml", "pydantic"]
# ///

import yaml
import json
import os
import sys
from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field

# Paths
AGENT_CONFIG_YAML = "dotfiles/agent-config.yaml"
CLAUDE_SETTINGS = "dotfiles/claude/.claude/settings.json"
GEMINI_SETTINGS_SRC = "dotfiles/gemini/.gemini/settings.json"

# System-wide paths for user reference
CLAUDE_SYSTEM_PATH = "~/.claude/settings.json"
GEMINI_SYSTEM_PATH = "~/.gemini/settings.json"

# Mappings
CLAUDE_MAP = {
    "events": {"post-tool-use": "PostToolUse", "finish": "Stop", "pre-tool-use": "PreToolUse"},
    "tools": {"edit": "Edit|Write|MultiEdit", "bash": "Bash"}
}
GEMINI_MAP = {
    "events": {"post-tool-use": "AfterTool", "finish": "AfterAgent", "pre-tool-use": "BeforeTool"},
    "tools": {"edit": "edit_file|write_file|smart_edit", "bash": "run_shell_command"}
}

# --- Pydantic Models ---

class Hook(BaseModel):
    name: str
    event: str
    tools: Optional[List[str]] = None
    commands: List[str]

class AgentSettings(BaseModel):
    allow: List[str] = Field(default_factory=list)
    deny: List[str] = Field(default_factory=list)
    hooks: List[Hook] = Field(default_factory=list)
    settings: Dict[str, Any] = Field(default_factory=dict)

    def merge_with(self, other: "AgentSettings") -> "AgentSettings":
        """Merges another AgentSettings into this one, returning a new instance."""
        
        # Merge lists with simple deduplication for strings
        merged_allow = sorted(list(set(self.allow + other.allow)))
        merged_deny = sorted(list(set(self.deny + other.deny)))
        
        # Concatenate hooks (complex objects are harder to dedup securely, 
        # but naively checking name might be enough. For now, just concat)
        merged_hooks = self.hooks + other.hooks
        
        # recursive dict merge for settings
        merged_settings = self._merge_dicts(self.settings, other.settings)

        return AgentSettings(
            allow=merged_allow,
            deny=merged_deny,
            hooks=merged_hooks,
            settings=merged_settings
        )

    def _merge_dicts(self, d1: Dict[str, Any], d2: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merges d2 into d1."""
        result = d1.copy()
        for k, v in d2.items():
            if k in result and isinstance(result[k], dict) and isinstance(v, dict):
                result[k] = self._merge_dicts(result[k], v)
            else:
                result[k] = v
        return result

class Config(BaseModel):
    common: AgentSettings = Field(default_factory=AgentSettings)
    claude: AgentSettings = Field(default_factory=AgentSettings)
    gemini: AgentSettings = Field(default_factory=AgentSettings)

    def get_effective_config(self, agent_name: str) -> AgentSettings:
        specific = getattr(self, agent_name, AgentSettings())
        return self.common.merge_with(specific)

# --- Helper Functions ---

def load_yaml_config(path) -> Config:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return Config(**data)

def load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(f"⚠️ Warning: Could not parse JSON from {path}. Starting fresh.")
        return {}

def build_hooks_config(hooks_list: List[Hook], mapping: Dict):
    """Builds the hooks configuration object for a specific tool."""
    hooks_config = {}
    
    for hook in hooks_list:
        target_event = mapping["events"].get(hook.event)
        
        if not target_event:
            continue
            
        if target_event not in hooks_config:
            hooks_config[target_event] = []
            
        # Build matcher
        matcher = None
        if hook.tools:
            matcher_parts = [mapping["tools"].get(t, t) for t in hook.tools]
            matcher = "|".join(matcher_parts)
            
        # Build commands
        commands = [{"type": "command", "command": cmd} for cmd in hook.commands]
        
        # Construct HookDefinition
        hook_def = {"hooks": commands}
        if matcher:
            hook_def["matcher"] = matcher
            
        hooks_config[target_event].append(hook_def)
        
    return hooks_config

def format_claude_permission(cmd: str) -> Optional[str]:
    """Formats a command for Claude Code permissions."""
    # Claude's parser fails on commands with parentheses like the fork bomb
    if "(" in cmd or ")" in cmd:
        print(f"⚠️  Skipping Claude permission for complex command: {cmd}")
        return None

    if cmd.endswith("*"):
        # Claude uses :* for prefix matching instead of *
        return f"Bash({cmd[:-1]}:*)"
    
    return f"Bash({cmd})"

def format_gemini_permission(cmd: str) -> str:
    """Formats a command for Gemini CLI permissions."""
    if cmd.endswith("*"):
        # Gemini handles prefix matching implicitly if we provide the prefix.
        return f"run_shell_command({cmd[:-1].strip()})"
    return f"run_shell_command({cmd})"

# --- Update Logic ---

def update_claude_settings(final_config: AgentSettings):
    """Updates Claude Code settings.json"""
    settings = load_json(CLAUDE_SETTINGS)
    
    # Permissions
    allow_cmds = [format_claude_permission(c) for c in final_config.allow]
    deny_cmds = [format_claude_permission(c) for c in final_config.deny]
    
    if "permissions" not in settings:
        settings["permissions"] = {}
    
    settings["permissions"]["allow"] = sorted([c for c in allow_cmds if c])
    settings["permissions"]["deny"] = sorted([c for c in deny_cmds if c])

    # Hooks
    if final_config.hooks:
        settings["hooks"] = build_hooks_config(final_config.hooks, CLAUDE_MAP)

    # Apply raw settings overrides
    if final_config.settings:
        # We re-use the merge logic from the class for convenience, though strictly we are merging dicts
        settings = AgentSettings(settings={})._merge_dicts(settings, final_config.settings)

    with open(CLAUDE_SETTINGS, "w") as f:
        json.dump(settings, f, indent=2)
    print(f"✅ Updated Claude Code config: {CLAUDE_SETTINGS}")

def update_gemini_settings(final_config: AgentSettings):
    """Updates Gemini CLI settings.json (merging with existing)"""
    settings = load_json(GEMINI_SETTINGS_SRC)

    if "tools" not in settings:
        settings["tools"] = {}

    # Permissions
    gemini_allow = [format_gemini_permission(c) for c in final_config.allow]
    gemini_deny = [format_gemini_permission(c) for c in final_config.deny]

    # Preserve non-shell allowed tools
    existing_allowed = settings["tools"].get("allowed", [])
    existing_exclude = settings["tools"].get("exclude", [])
    
    preserved_allowed = [t for t in existing_allowed if not t.startswith("run_shell_command(")]
    preserved_exclude = [t for t in existing_exclude if not t.startswith("run_shell_command(")]

    settings["tools"]["allowed"] = preserved_allowed + sorted(gemini_allow)
    settings["tools"]["exclude"] = preserved_exclude + sorted(gemini_deny)

    # Hooks
    if final_config.hooks:
        settings["hooks"] = build_hooks_config(final_config.hooks, GEMINI_MAP)

    # Apply raw settings overrides
    if final_config.settings:
        settings = AgentSettings(settings={})._merge_dicts(settings, final_config.settings)

    # Ensure directory exists
    os.makedirs(os.path.dirname(GEMINI_SETTINGS_SRC), exist_ok=True)

    with open(GEMINI_SETTINGS_SRC, "w") as f:
        json.dump(settings, f, indent=2)
    print(f"✅ Updated Gemini CLI config: {GEMINI_SETTINGS_SRC}")

def main():
    if not os.path.exists(AGENT_CONFIG_YAML):
        print(f"❌ Error: {AGENT_CONFIG_YAML} not found.")
        sys.exit(1)

    print(f"📖 Reading configuration from {AGENT_CONFIG_YAML}...")
    try:
        config = load_yaml_config(AGENT_CONFIG_YAML)
    except Exception as e:
        print(f"❌ Configuration Error: {e}")
        sys.exit(1)

    # Get merged/effective configs for each agent
    claude_config = config.get_effective_config("claude")
    gemini_config = config.get_effective_config("gemini")

    update_claude_settings(claude_config)
    update_gemini_settings(gemini_config)
    
    print("\n🎉 Sync Complete!")
    print(f"🔍 Inspect Claude settings: cat {CLAUDE_SYSTEM_PATH}")
    print(f"🔍 Inspect Gemini settings: cat {GEMINI_SYSTEM_PATH}")

if __name__ == "__main__":
    main()