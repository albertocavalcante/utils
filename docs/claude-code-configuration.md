# Claude Code Configuration & Hooks

This document outlines the configuration schema and "awesome" hooks for
[Claude Code](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview),
ensuring a safe, automated, and efficient AI coding assistant.

## Configuration Schema

To enable auto-completion and validation in editors like VS Code, add the
`$schema` property to your `settings.json`.

**Schema URL:** `https://json.schemastore.org/claude-code-settings.json`

**Example `settings.json` with Schema:**

```json
{
  "$schema": "https://json.schemastore.org/claude-code-settings.json",
  "permissions": {
    "allow": ["Bash(git status)"],
    "deny": ["Bash(rm -rf /)"]
  }
}
```

## Awesome Hooks

Hooks allow you to automate tasks before or after Claude Code tools run. Define
these in your `settings.json`.

### 1. Auto-Format & Lint (Post-Write)

Automatically formats and lints code after Claude edits a file. This hook checks
for the existence of configuration files (`dprint.json`, `ruff.toml`) to ensure
it only runs in relevant projects.

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "if [ -f dprint.json ]; then dprint fmt; fi"
          },
          {
            "type": "command",
            "command": "if [ -f ruff.toml ] || [ -f pyproject.toml ]; then ruff check --fix .; fi"
          }
        ]
      }
    ]
  }
}
```

### 2. Task Completion Sound (Stop)

Plays a subtle sound when Claude finishes a task (stops generating). This is
great for long-running operations.

**MacOS:**

```json
{
  "hooks": {
    "Stop": [
      {
        "type": "command",
        "command": "afplay /System/Library/Sounds/Glass.aiff >/dev/null 2>&1 &"
      }
    ]
  }
}
```

### 3. Safety Check (Pre-Tool Use)

A conceptual hook to double-check dangerous operations if you need logic more
complex than a simple allow/deny list.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Safety check: analyzing command...' && # add your logic here"
          }
        ]
      }
    ]
  }
}
```

## Permission Best Practices

- **Deny List:** Explicitly block catastrophic commands (`rm -rf /`, `mkfs`,
  `dd`, etc.).
- **Allow List:** Explicitly allow safe, read-only commands (`git status`,
  `gh repo view`, `ls`, `cat`) to reduce friction.
- **Wildcards:** Use `Bash(command:*)` carefully. Prefer specific subcommands
  when possible.

## Reference

- [Official Claude Code Documentation](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview)
