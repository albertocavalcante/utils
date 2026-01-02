#!/usr/bin/env -S uv run
# /// script
# dependencies = [
#   "pyyaml>=6.0",
#   "pydantic>=2.0",
#   "tomli>=2.0",
#   "typer>=0.12.0",
#   "rich>=13.0",
# ]
# ///

import yaml
import tomli
import json
import os
import sys
from typing import List, Dict, Optional, Any, Union
from pydantic import BaseModel, Field
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import print as rprint

# --- App & Logger ---
app = typer.Typer(help="Sync Agent Configurations between YAML/TOML and target JSONs.")
console = Console()

class Log:
    VERBOSE = False

    @staticmethod
    def info(msg: str):
        console.print(f"[bold blue]ℹ️  INFO:[/bold blue] {msg}")

    @staticmethod
    def success(msg: str):
        console.print(f"[bold green]✅ SUCCESS:[/bold green] {msg}")

    @staticmethod
    def warn(msg: str):
        console.print(f"[bold yellow]⚠️  WARNING:[/bold yellow] {msg}")

    @staticmethod
    def error(msg: str):
        console.print(f"[bold red]❌ ERROR:[/bold red] {msg}")

    @staticmethod
    def debug(msg: str):
        if Log.VERBOSE:
            console.print(f"[dim cyan]🔍 DEBUG: {msg}[/dim cyan]")

# --- Constants ---
AGENT_CONFIG_YAML = "dotfiles/agent-config.yaml"
AGENT_CONFIG_TOML = "dotfiles/agent-config.toml"
CLAUDE_SETTINGS = "dotfiles/claude/.claude/settings.json"
GEMINI_SETTINGS_SRC = "dotfiles/gemini/.gemini/settings.json"

# macOS Specific Paths
KIRO_SETTINGS = os.path.expanduser("~/Library/Application Support/Kiro/User/settings.json")
ANTIGRAVITY_SETTINGS = os.path.expanduser("~/Library/Application Support/Antigravity/User/settings.json")

CLAUDE_SYSTEM_PATH = "~/.claude/settings.json"
GEMINI_SYSTEM_PATH = "~/.gemini/settings.json"
KIRO_SYSTEM_PATH = "~/Library/Application Support/Kiro/User/settings.json"
ANTIGRAVITY_SYSTEM_PATH = "~/Library/Application Support/Antigravity/User/settings.json"

CLAUDE_MAP = {
    "events": {"post-tool-use": "PostToolUse", "finish": "Stop", "pre-tool-use": "PreToolUse"},
    "tools": {"edit": "Edit|Write|MultiEdit", "bash": "Bash"}
}
GEMINI_MAP = {
    "events": {"post-tool-use": "AfterTool", "finish": "AfterAgent", "pre-tool-use": "BeforeTool"},
    "tools": {"edit": "edit_file|write_file|smart_edit", "bash": "run_shell_command"}
}

KNOWN_CLAUDE_ENV_VARS = {
    # Authentication & API
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_CUSTOM_HEADERS", "ANTHROPIC_FOUNDRY_API_KEY",
    "AWS_BEARER_TOKEN_BEDROCK", "CLAUDE_CODE_API_KEY_HELPER_TTL_MS",
    "CLAUDE_CODE_CLIENT_CERT", "CLAUDE_CODE_CLIENT_KEY", "CLAUDE_CODE_CLIENT_KEY_PASSPHRASE",
    # Model Selection
    "ANTHROPIC_MODEL", "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
    "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_SMALL_FAST_MODEL", "ANTHROPIC_SMALL_FAST_MODEL_AWS_REGION",
    "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_FOUNDRY",
    "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_SKIP_BEDROCK_AUTH", "CLAUDE_CODE_SKIP_FOUNDRY_AUTH",
    "CLAUDE_CODE_SKIP_VERTEX_AUTH",
    "VERTEX_REGION_CLAUDE_3_5_HAIKU", "VERTEX_REGION_CLAUDE_3_7_SONNET",
    "VERTEX_REGION_CLAUDE_4_0_OPUS", "VERTEX_REGION_CLAUDE_4_0_SONNET", "VERTEX_REGION_CLAUDE_4_1_OPUS",
    # Network
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    # Shell
    "BASH_DEFAULT_TIMEOUT_MS", "BASH_MAX_OUTPUT_LENGTH", "BASH_MAX_TIMEOUT_MS",
    "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR", "CLAUDE_ENV_FILE", "CLAUDE_CODE_SHELL_PREFIX",
    "SHELL", "EDITOR", "VISUAL",
    # System
    "CLAUDE_CONFIG_DIR", "CLAUDE_LOG_LEVEL", "CLAUDE_DEBUG", "CLAUDE_CODE_IDE_SKIP_AUTO_INSTALL",
    "CLAUDE_CODE_DISABLE_TERMINAL_TITLE", "CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS", "CLAUDE_CODE_OTEL_HEADERS_HELPER_DEBOUNCE_MS",
    "MAX_MCP_OUTPUT_TOKENS", "MAX_THINKING_TOKENS", "MCP_TIMEOUT", "MCP_TOOL_TIMEOUT",
    "SLASH_COMMAND_TOOL_CHAR_BUDGET", "USE_BUILTIN_RIPGREP",
    # Disabling Features
    "DISABLE_AUTOUPDATER", "DISABLE_BUG_COMMAND", "DISABLE_COST_WARNINGS", "DISABLE_ERROR_REPORTING",
    "DISABLE_NON_ESSENTIAL_MODEL_CALLS", "DISABLE_PROMPT_CACHING", "DISABLE_PROMPT_CACHING_HAIKU",
    "DISABLE_PROMPT_CACHING_OPUS", "DISABLE_PROMPT_CACHING_SONNET", "DISABLE_TELEMETRY",
    "CI"
}

# --- Pydantic Models ---

class Hook(BaseModel):
    name: str
    event: str
    tools: Optional[List[str]] = None
    commands: List[str]

class EnvSettings(BaseModel):
    vars: Dict[str, str] = Field(default_factory=dict)
    allow: List[str] = Field(default_factory=list)
    block: List[str] = Field(default_factory=list)

    def merge_with(self, other: "EnvSettings") -> "EnvSettings":
        merged_vars = self.vars.copy()
        merged_vars.update(other.vars)
        merged_allow = sorted(list(set(self.allow + other.allow)))
        merged_block = sorted(list(set(self.block + other.block)))
        return EnvSettings(vars=merged_vars, allow=merged_allow, block=merged_block)

class NetworkSettings(BaseModel):
    proxy: Optional[str] = None

    def merge_with(self, other: "NetworkSettings") -> "NetworkSettings":
        return NetworkSettings(proxy=other.proxy if other.proxy is not None else self.proxy)

class CommandGroup(BaseModel):
    allow: List[str] = Field(default_factory=list)
    deny: List[str] = Field(default_factory=list)
    commands: Dict[str, "CommandGroup"] = Field(default_factory=dict)

    def merge_with(self, other: "CommandGroup") -> "CommandGroup":
        merged_allow = sorted(list(set(self.allow + other.allow)))
        merged_deny = sorted(list(set(self.deny + other.deny)))
        
        merged_commands = self.commands.copy()
        for tool, group in other.commands.items():
            if tool in merged_commands:
                merged_commands[tool] = merged_commands[tool].merge_with(group)
            else:
                merged_commands[tool] = group
                
        return CommandGroup(allow=merged_allow, deny=merged_deny, commands=merged_commands)

    def get_flat_lists(self, prefix: str) -> (List[str], List[str]):
        flat_allow = []
        flat_deny = []
        
        for cmd in self.allow:
            flat_allow.append(f"{prefix} *" if cmd == "*" else f"{prefix} {cmd}")
        for cmd in self.deny:
            flat_deny.append(f"{prefix} *" if cmd == "*" else f"{prefix} {cmd}")
            
        for tool, group in self.commands.items():
            sub_allow, sub_deny = group.get_flat_lists(f"{prefix} {tool}")
            flat_allow.extend(sub_allow)
            flat_deny.extend(sub_deny)
            
        return flat_allow, flat_deny

class AgentSettings(BaseModel):
    allow: List[str] = Field(default_factory=list)
    deny: List[str] = Field(default_factory=list)
    commands: Dict[str, CommandGroup] = Field(default_factory=dict)
    hooks: List[Hook] = Field(default_factory=list)
    env: EnvSettings = Field(default_factory=EnvSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    settings: Dict[str, Any] = Field(default_factory=dict)

    def merge_with(self, other: "AgentSettings") -> "AgentSettings":
        merged_allow = sorted(list(set(self.allow + other.allow)))
        merged_deny = sorted(list(set(self.deny + other.deny)))
        
        merged_commands = self.commands.copy()
        for tool, group in other.commands.items():
            if tool in merged_commands:
                merged_commands[tool] = merged_commands[tool].merge_with(group)
            else:
                merged_commands[tool] = group

        merged_hooks = self.hooks + other.hooks
        merged_env = self.env.merge_with(other.env)
        merged_network = self.network.merge_with(other.network)
        merged_settings = self._merge_dicts(self.settings, other.settings)

        return AgentSettings(
            allow=merged_allow,
            deny=merged_deny,
            commands=merged_commands,
            hooks=merged_hooks,
            env=merged_env,
            network=merged_network,
            settings=merged_settings
        )

    def get_flat_lists(self):
        final_allow = set(self.allow)
        final_deny = set(self.deny)

        for tool, group in self.commands.items():
            g_allow, g_deny = group.get_flat_lists(tool)
            final_allow.update(g_allow)
            final_deny.update(g_deny)
        
        return sorted(list(final_allow)), sorted(list(final_deny))

    def _merge_dicts(self, d1: Dict[str, Any], d2: Dict[str, Any]) -> Dict[str, Any]:
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

def load_yaml_config(path: str) -> Config:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return Config(**data)

def load_toml_config(path: str) -> Config:
    with open(path, "rb") as f:
        data = tomli.load(f)
    return Config(**data)

def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        Log.warn(f"Could not parse JSON from {path}. Starting fresh.")
        return {}

def build_hooks_config(hooks_list: List[Hook], mapping: Dict) -> Dict:
    hooks_config = {}
    for hook in hooks_list:
        target_event = mapping["events"].get(hook.event)
        if not target_event:
            continue
        if target_event not in hooks_config:
            hooks_config[target_event] = []
        matcher = None
        if hook.tools:
            matcher_parts = [mapping["tools"].get(t, t) for t in hook.tools]
            matcher = "|".join(matcher_parts)
        commands = [{"type": "command", "command": cmd} for cmd in hook.commands]
        hook_def = {"hooks": commands}
        if matcher:
            hook_def["matcher"] = matcher
        hooks_config[target_event].append(hook_def)
    return hooks_config

def format_claude_permission(cmd: str) -> Optional[str]:
    if "(" in cmd or ")" in cmd:
        Log.warn(f"Skipping Claude permission for complex command: {cmd}")
        return None
    if cmd.endswith("*"):
        return f"Bash({cmd[:-1]}:*)"
    return f"Bash({cmd})"

def format_gemini_permission(cmd: str) -> str:
    if cmd.endswith("*"):
        return f"run_shell_command({cmd[:-1].strip()})"
    return f"run_shell_command({cmd})"

# --- Update Logic ---

def update_claude_settings(final_config: AgentSettings):
    settings = load_json(CLAUDE_SETTINGS)
    flat_allow, flat_deny = final_config.get_flat_lists()
    
    allow_cmds = [format_claude_permission(c) for c in flat_allow]
    deny_cmds = [format_claude_permission(c) for c in flat_deny]
    
    # Filter out Nones
    allow_cmds = [c for c in allow_cmds if c]
    deny_cmds = [c for c in deny_cmds if c]

    if "permissions" not in settings:
        settings["permissions"] = {}
    settings["permissions"]["allow"] = sorted(allow_cmds)
    settings["permissions"]["deny"] = sorted(deny_cmds)
    
    env_vars = final_config.env.vars.copy()
    if final_config.network.proxy:
        if "HTTP_PROXY" not in env_vars:
            env_vars["HTTP_PROXY"] = final_config.network.proxy
        if "HTTPS_PROXY" not in env_vars:
            env_vars["HTTPS_PROXY"] = final_config.network.proxy
    
    unknown_vars = [k for k in env_vars.keys() if k not in KNOWN_CLAUDE_ENV_VARS]
    if unknown_vars:
        Log.warn(f"Unknown Claude env vars: {', '.join(unknown_vars)}")
        
    if env_vars:
        settings["env"] = env_vars
    if final_config.hooks:
        settings["hooks"] = build_hooks_config(final_config.hooks, CLAUDE_MAP)
    if final_config.settings:
        settings = final_config._merge_dicts(settings, final_config.settings)
        
    os.makedirs(os.path.dirname(CLAUDE_SETTINGS), exist_ok=True)
    with open(CLAUDE_SETTINGS, "w") as f:
        json.dump(settings, f, indent=2)
    Log.success(f"Updated Claude Code config: {CLAUDE_SETTINGS}")

def update_gemini_settings(final_config: AgentSettings):
    settings = load_json(GEMINI_SETTINGS_SRC)
    if "tools" not in settings:
        settings["tools"] = {}
        
    flat_allow, flat_deny = final_config.get_flat_lists()
    gemini_allow = [format_gemini_permission(c) for c in flat_allow]
    gemini_deny = [format_gemini_permission(c) for c in flat_deny]
    
    existing_allowed = settings["tools"].get("allowed", [])
    existing_exclude = settings["tools"].get("exclude", [])
    
    preserved_allowed = [t for t in existing_allowed if not t.startswith("run_shell_command(")]
    preserved_exclude = [t for t in existing_exclude if not t.startswith("run_shell_command(")]
    
    settings["tools"]["allowed"] = preserved_allowed + sorted(gemini_allow)
    settings["tools"]["exclude"] = preserved_exclude + sorted(gemini_deny)
    
    if final_config.env.allow:
        settings["allowedEnvironmentVariables"] = final_config.env.allow
    if final_config.env.block:
        settings["blockedEnvironmentVariables"] = final_config.env.block
    if final_config.network.proxy:
        settings["proxy"] = final_config.network.proxy
    if final_config.hooks:
        settings["hooks"] = build_hooks_config(final_config.hooks, GEMINI_MAP)
    if final_config.settings:
        settings = final_config._merge_dicts(settings, final_config.settings)
        
    os.makedirs(os.path.dirname(GEMINI_SETTINGS_SRC), exist_ok=True)
    with open(GEMINI_SETTINGS_SRC, "w") as f:
        json.dump(settings, f, indent=2)
    Log.success(f"Updated Gemini CLI config: {GEMINI_SETTINGS_SRC}")

def update_kiro_settings(final_config: AgentSettings):
    """
    Updates Kiro Desktop settings (Single Source of Truth).
    TODO: Reconcile manual IDE allow-list changes occasionally.
    """
    if not os.path.exists(KIRO_SETTINGS):
        Log.debug(f"Kiro settings not found at {KIRO_SETTINGS}. Skipping.")
        return

    settings = load_json(KIRO_SETTINGS)
    flat_allow, _ = final_config.get_flat_lists()
    
    # Synapse is the Single Source of Truth for trusted commands.
    settings["kiroAgent.trustedCommands"] = sorted(flat_allow)
    
    with open(KIRO_SETTINGS, "w") as f:
        json.dump(settings, f, indent=4)
    Log.success(f"Updated Kiro Desktop config: {KIRO_SETTINGS}")

def update_antigravity_settings(final_config: AgentSettings):
    """
    Updates Antigravity Desktop settings.
    """
    if not os.path.exists(ANTIGRAVITY_SETTINGS):
        Log.debug(f"Antigravity settings not found at {ANTIGRAVITY_SETTINGS}. Skipping.")
        return

    settings = load_json(ANTIGRAVITY_SETTINGS)
    flat_allow, _ = final_config.get_flat_lists()
    
    # Synapse is the Single Source of Truth for trusted commands.
    # Assuming 'antigravityAgent.trustedCommands' follows the Kiro pattern.
    settings["antigravityAgent.trustedCommands"] = sorted(flat_allow)
    
    with open(ANTIGRAVITY_SETTINGS, "w") as f:
        json.dump(settings, f, indent=4)
    Log.success(f"Updated Antigravity Desktop config: {ANTIGRAVITY_SETTINGS}")

@app.command()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose debug logging.")
):
    """
    Synapse: A configuration synchronizer for AI Agents.
    Reads from agent-config.yaml/toml and updates Claude, Gemini, Kiro, and Antigravity settings.
    """
    Log.VERBOSE = verbose
    
    console.print(Panel.fit("[bold magenta]Synapse Configuration Sync[/bold magenta]", border_style="magenta"))
    
    config = None
    if os.path.exists(AGENT_CONFIG_TOML):
        Log.info(f"Reading configuration from [bold]{AGENT_CONFIG_TOML}[/bold]...")
        try:
            config = load_toml_config(AGENT_CONFIG_TOML)
        except Exception as e:
            Log.error(f"Configuration Error (TOML): {e}")
            raise typer.Exit(code=1)
    elif os.path.exists(AGENT_CONFIG_YAML):
        Log.info(f"Reading configuration from [bold]{AGENT_CONFIG_YAML}[/bold]...")
        try:
            config = load_yaml_config(AGENT_CONFIG_YAML)
        except Exception as e:
            Log.error(f"Configuration Error (YAML): {e}")
            raise typer.Exit(code=1)
    else:
        Log.error("No configuration found (agent-config.yaml or .toml).")
        raise typer.Exit(code=1)

    claude_config = config.get_effective_config("claude")
    gemini_config = config.get_effective_config("gemini")
    
    update_claude_settings(claude_config)
    update_gemini_settings(gemini_config)
    update_kiro_settings(claude_config) # Using Claude's effective config for Kiro
    update_antigravity_settings(claude_config) # Using Claude's effective config for Antigravity
    
    # Summary Table
    table = Table(title="Sync Status", show_header=True, header_style="bold cyan")
    table.add_column("Agent", style="dim")
    table.add_column("Status", style="green")
    table.add_column("Path")
    
    table.add_row("Claude", "Updated", CLAUDE_SYSTEM_PATH)
    table.add_row("Gemini", "Updated", GEMINI_SYSTEM_PATH)
    if os.path.exists(KIRO_SETTINGS):
        table.add_row("Kiro", "Updated", KIRO_SYSTEM_PATH)
    if os.path.exists(ANTIGRAVITY_SETTINGS):
        table.add_row("Antigravity", "Updated", ANTIGRAVITY_SYSTEM_PATH)
    
    console.print("\n", table)
    console.print("\n[bold green]🎉 Sync Complete![/bold green]")

if __name__ == "__main__":
    Hook.model_rebuild()
    EnvSettings.model_rebuild()
    NetworkSettings.model_rebuild()
    CommandGroup.model_rebuild()
    AgentSettings.model_rebuild()
    Config.model_rebuild()
    app()
