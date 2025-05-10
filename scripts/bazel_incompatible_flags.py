#!/usr/bin/env -S uv --quiet run --script
# /// script
# requires-python = ">=3.13"
# dependencies = [
#   "typer>=0.15.3",
#   "pydantic>=2.11.4",
#   "pyperclip>=1.9.0",
# ]
# ///

# type: ignore[import]

import os
import re
import shutil
import tempfile
import subprocess
from typing import List, Tuple, Dict, Optional, Set, Any
from pathlib import Path
import platform
import json
from functools import lru_cache
import time

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from pydantic import BaseModel, Field

# Models for structured data
class IncompatibleFlag(BaseModel):
    """Model representing an incompatible flag."""
    name: str
    description: str = Field(default="")
    available: bool = Field(default=True)
    
class FlagResult(BaseModel):
    """Model for the result of flag operations."""
    flags: List[IncompatibleFlag] = Field(default_factory=list)
    command: str
    bazel_version: str = Field(default="")
    error: Optional[str] = None

# Console setup
console = Console()
app = typer.Typer(help="Extract and display all incompatible flags for Bazel commands.")

# Cache directory for storing flag information
CACHE_DIR = Path(tempfile.gettempdir()) / "bazel_incompatible_flags"

def ensure_cache_dir() -> None:
    """Ensure the cache directory exists."""
    os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(bazel_path: str, cmd: str) -> Path:
    """Get the cache path for the given Bazel path and command."""
    bazel_version = get_bazel_version(bazel_path)
    return CACHE_DIR / f"{bazel_version}_{cmd}_flags.json"

def save_to_cache(result: FlagResult, cache_path: Path) -> None:
    """Save the flag result to cache."""
    ensure_cache_dir()
    with open(cache_path, "w") as f:
        f.write(result.model_dump_json(indent=2))

def load_from_cache(cache_path: Path) -> Optional[FlagResult]:
    """Load the flag result from cache if it exists and is recent."""
    if not cache_path.exists():
        return None
        
    # Check if cache is older than a day
    if (os.path.getmtime(cache_path) < (time.time() - 86400)):
        return None
        
    try:
        with open(cache_path, "r") as f:
            data = json.load(f)
        return FlagResult.model_validate(data)
    except Exception:
        return None

def run_bazel_command(cmd: List[str]) -> Tuple[str, int]:
    """
    Run a Bazel command and return its output and return code.
    
    Args:
        cmd: The Bazel command to run as a list of strings
        
    Returns:
        A tuple containing the output and return code
    """
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=30  # Add timeout to avoid hanging
        )
        return result.stdout + result.stderr, result.returncode
    except subprocess.TimeoutExpired:
        return "Command timed out after 30 seconds", 1
    except Exception as e:
        console.print(f"[bold red]Error running Bazel command:[/] {e}")
        return f"Error: {str(e)}", 1

def is_bazel_installed(bazel_path: str) -> bool:
    """Check if Bazel is installed and accessible."""
    if os.path.isfile(bazel_path):
        return True
    return shutil.which(bazel_path) is not None

@lru_cache(maxsize=10)
def get_bazel_version(bazel_path: str) -> str:
    """Get the Bazel version."""
    output, return_code = run_bazel_command([bazel_path, "version"])
    if return_code != 0:
        return "unknown"
    
    version_match = re.search(r'Build label: (\d+\.\d+\.\d+)', output)
    if version_match:
        return version_match.group(1)
    return "unknown"

def get_valid_bazel_commands(bazel_path: str) -> Set[str]:
    """Get a set of valid Bazel commands."""
    output, return_code = run_bazel_command([bazel_path, "help"])
    if return_code != 0:
        return set()
    
    # Extract commands from help output
    commands = set()
    for line in output.splitlines():
        if re.match(r'^\s+\w+\s+-', line):
            cmd = line.strip().split()[0]
            commands.add(cmd)
    
    # Add common commands that might not be in the help output
    common_commands = {"build", "test", "run", "query", "clean", "sync"}
    commands.update(common_commands)
    
    return commands

def try_get_flag_description(bazel_path: str, flag: str) -> str:
    """Try to get a description for the flag."""
    # Remove the -- prefix for querying
    flag_name = flag.lstrip("-")
    
    # Try to get help for this specific flag
    output, _ = run_bazel_command([bazel_path, "help", f"--{flag_name}"])
    
    # Extract description if available
    description_match = re.search(r'--\[no\]' + flag_name + r'\s+(.+?)(\n|$)', output)
    if description_match:
        return description_match.group(1).strip()
    
    return ""

def verify_flag_availability(bazel_path: str, flag: str) -> bool:
    """Verify if the flag is actually available in the current Bazel version."""
    # Simple test command that should work with any flag
    cmd = [bazel_path, "help", flag]
    _, return_code = run_bazel_command(cmd)
    
    # If return code is 0 or 2 (help displayed), the flag exists
    # Return code 1 typically means the flag doesn't exist
    return return_code in (0, 2)

def get_incompatible_flags(bazel_path: str, cmd: str, use_cache: bool = True) -> FlagResult:
    """
    Get all incompatible flags for the specified Bazel command.
    
    Args:
        bazel_path: Path to the Bazel binary
        cmd: The Bazel command to inspect
        use_cache: Whether to use cached results if available
        
    Returns:
        A FlagResult object containing the flags and metadata
    """
    # Check if Bazel is installed
    if not is_bazel_installed(bazel_path):
        return FlagResult(
            flags=[],
            command=cmd,
            error=f"Bazel not found at '{bazel_path}' and not in PATH"
        )
    
    # Get Bazel version
    bazel_version = get_bazel_version(bazel_path)
    
    # Check if command is valid
    valid_commands = get_valid_bazel_commands(bazel_path)
    if cmd not in valid_commands:
        return FlagResult(
            flags=[],
            command=cmd,
            bazel_version=bazel_version,
            error=f"Invalid Bazel command: '{cmd}'. Valid commands: {', '.join(sorted(valid_commands))}"
        )
    
    # Check cache if enabled
    cache_path = get_cache_path(bazel_path, cmd)
    if use_cache:
        cached_result = load_from_cache(cache_path)
        if cached_result:
            return cached_result
    
    # Check if flags are specified in environment variable
    env_flags_str = os.environ.get("BAZELISK_INCOMPATIBLE_FLAGS", "")
    env_flags = []
    if env_flags_str:
        # Return flags from environment variable
        env_flags = env_flags_str.split(",")
        flags = [
            IncompatibleFlag(
                name=flag,
                description="From BAZELISK_INCOMPATIBLE_FLAGS environment variable",
                available=verify_flag_availability(bazel_path, flag)
            )
            for flag in env_flags
        ]
        result = FlagResult(flags=flags, command=cmd, bazel_version=bazel_version)
        save_to_cache(result, cache_path)
        return result
    
    # Run bazel help command to get flags
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Fetching incompatible flags..."),
        transient=True
    ) as progress:
        progress.add_task("fetch", total=None)
        output, return_code = run_bazel_command([bazel_path, "help", cmd, "--short"])
    
    if return_code != 0:
        return FlagResult(
            flags=[],
            command=cmd,
            bazel_version=bazel_version,
            error=f"Failed to get help for Bazel command '{cmd}'"
        )
    
    # Parse flags using regex
    re_pattern = r'(?m)^\s*--\[no\](incompatible_\w+)$'
    matches = re.findall(re_pattern, output)
    
    # Format flags with -- prefix and get descriptions
    with Progress(
        SpinnerColumn(),
        TextColumn("[cyan]Processing flags information..."),
        transient=True
    ) as progress:
        progress.add_task("process", total=None)
        flags = []
        for match in sorted(matches):
            flag_name = f"--{match}"
            description = try_get_flag_description(bazel_path, flag_name)
            available = verify_flag_availability(bazel_path, flag_name)
            
            flags.append(IncompatibleFlag(
                name=flag_name,
                description=description,
                available=available
            ))
    
    result = FlagResult(flags=flags, command=cmd, bazel_version=bazel_version)
    save_to_cache(result, cache_path)
    return result

def display_flags(result: FlagResult, show_unavailable: bool = False) -> None:
    """
    Display the incompatible flags in a rich formatted table.
    
    Args:
        result: The FlagResult containing flags to display
        show_unavailable: Whether to show unavailable flags
    """
    if result.error:
        console.print(f"[bold red]Error:[/] {result.error}")
        return
    
    flags = result.flags
    if not flags:
        console.print(f"[yellow]No incompatible flags found for command: [bold]{result.command}[/bold][/]")
        return
    
    # Filter flags if needed
    display_flags = flags
    if not show_unavailable:
        display_flags = [f for f in flags if f.available]
    
    if not display_flags:
        console.print(f"[yellow]No available incompatible flags found for command: [bold]{result.command}[/bold][/]")
        return
    
    # Create table with flags
    table = Table(
        title=f"Incompatible Flags for 'bazel {result.command}' (version: {result.bazel_version})"
    )
    table.add_column("Flag", style="cyan")
    table.add_column("Description", style="green")
    table.add_column("Available", style="yellow")
    
    for flag in display_flags:
        table.add_row(
            flag.name,
            flag.description or "No description available",
            "✓" if flag.available else "✗"
        )
    
    console.print(table)
    
    # Only include available flags in the environment variable
    available_flags = [f.name for f in flags if f.available]
    env_var_value = ",".join(available_flags)
    
    if available_flags:
        # Try to copy to clipboard
        try:
            import pyperclip
            pyperclip.copy(f'export BAZELISK_INCOMPATIBLE_FLAGS="{env_var_value}"')
            console.print("\n[green]✨ Environment variable command copied to clipboard! 📋[/]")
            
            # Show a preview
            console.print("\n[dim]Preview of copied command:[/]")
            preview = f'export BAZELISK_INCOMPATIBLE_FLAGS="..."'
            console.print(f"[dim]{preview}[/]")
            
            # For Windows users
            if platform.system() == "Windows":
                console.print("\n[dim]For Windows users, you can also use:[/]")
                console.print("[dim]• Command Prompt: set BAZELISK_INCOMPATIBLE_FLAGS=...[/]")
                console.print("[dim]• PowerShell: $env:BAZELISK_INCOMPATIBLE_FLAGS = \"...\"[/]")
                
        except ImportError:
            console.print("\n[yellow]📝 To copy commands to clipboard, install pyperclip:[/]")
            console.print("[dim]pip install pyperclip[/]")
            
            # Show the full command since we couldn't copy it
            env_panel = Panel(
                Syntax(f'export BAZELISK_INCOMPATIBLE_FLAGS="{env_var_value}"', "bash"),
                title="Environment Variable Setting",
                subtitle="Copy this command to use incompatible flags"
            )
            console.print(env_panel)

def create_output_file(result: FlagResult, output_path: str, format_type: str) -> None:
    """
    Create an output file with the incompatible flags.
    
    Args:
        result: The FlagResult containing flags
        output_path: Path to output file
        format_type: Format type ('json' or 'text')
    """
    available_flags = [f.name for f in result.flags if f.available]
    
    if format_type == "json":
        output_data = {
            "command": result.command,
            "bazel_version": result.bazel_version,
            "flags": [f.model_dump() for f in result.flags],
            "environment_variable": ",".join(available_flags)
        }
        with open(output_path, "w") as f:
            json.dump(output_data, f, indent=2)
    else:  # text format
        with open(output_path, "w") as f:
            f.write(f"Incompatible flags for 'bazel {result.command}' (version: {result.bazel_version}):\n\n")
            for flag in result.flags:
                status = "Available" if flag.available else "Unavailable"
                f.write(f"{flag.name} ({status})\n")
                if flag.description:
                    f.write(f"  Description: {flag.description}\n")
                f.write("\n")
            
            f.write("\nSuggested environment variable setting:\n")
            f.write(f'export BAZELISK_INCOMPATIBLE_FLAGS="{",".join(available_flags)}"\n')
            
            if platform.system() == "Windows":
                f.write("\nFor Windows Command Prompt:\n")
                f.write(f'set BAZELISK_INCOMPATIBLE_FLAGS={",".join(available_flags)}\n')
                
                f.write("\nFor Windows PowerShell:\n")
                f.write(f'$env:BAZELISK_INCOMPATIBLE_FLAGS = "{",".join(available_flags)}"\n')
    
    console.print(f"[green]Output written to: [bold]{output_path}[/bold][/]")

@app.command()
def main(
    cmd: str = typer.Argument("build", help="The Bazel command to inspect"),
    bazel_path: str = typer.Option(
        "bazel", "--bazel-path", "-b", 
        help="Path to the Bazel binary"
    ),
    output_format: str = typer.Option(
        "rich", "--format", "-f",
        help="Output format: 'rich' (default), 'plain', or 'json'"
    ),
    output_file: Optional[str] = typer.Option(
        None, "--output", "-o",
        help="Output file path (if not specified, output is displayed in console)"
    ),
    show_unavailable: bool = typer.Option(
        False, "--show-unavailable", "-u",
        help="Show flags that are not available in the current Bazel version"
    ),
    no_cache: bool = typer.Option(
        False, "--no-cache",
        help="Disable cache and force fetching fresh flag information"
    )
) -> None:
    """
    Extract and display all incompatible flags for Bazel commands.
    
    This tool helps you identify all incompatible flags for a specific Bazel command
    and generates the suggested value for the BAZELISK_INCOMPATIBLE_FLAGS environment variable.
    It works across Linux, macOS, and Windows.
    """
    # Get incompatible flags
    result = get_incompatible_flags(bazel_path, cmd, use_cache=not no_cache)
    
    # Handle output
    if output_file:
        if output_format == "json":
            create_output_file(result, output_file, "json")
        else:
            create_output_file(result, output_file, "text")
    elif output_format == "plain":
        # Simple plain text output
        if result.error:
            print(f"Error: {result.error}")
        elif not result.flags:
            print(f"No incompatible flags found for command: {cmd}")
        else:
            available_flags = [f.name for f in result.flags if f.available]
            
            print(f"Incompatible flags for 'bazel {cmd}' (version: {result.bazel_version}):")
            for flag in result.flags:
                if not show_unavailable and not flag.available:
                    continue
                    
                status = "Available" if flag.available else "Unavailable"
                print(f"  {flag.name} ({status})")
                if flag.description:
                    print(f"    Description: {flag.description}")
            
            if available_flags:
                print("\nSuggested environment variable setting:")
                print(f'export BAZELISK_INCOMPATIBLE_FLAGS="{",".join(available_flags)}"')
                
                if platform.system() == "Windows":
                    print("\nFor Windows Command Prompt:")
                    print(f'set BAZELISK_INCOMPATIBLE_FLAGS={",".join(available_flags)}')
                    
                    print("\nFor Windows PowerShell:")
                    print(f'$env:BAZELISK_INCOMPATIBLE_FLAGS = "{",".join(available_flags)}"')
    elif output_format == "json":
        # JSON output
        output_data = {
            "command": result.command,
            "bazel_version": result.bazel_version,
            "flags": [f.model_dump() for f in result.flags if show_unavailable or f.available],
            "environment_variable": ",".join([f.name for f in result.flags if f.available])
        }
        print(json.dumps(output_data, indent=2))
    else:
        # Rich formatted output
        display_flags(result, show_unavailable)

if __name__ == "__main__":
    # Create cache directory on startup
    ensure_cache_dir()
    app()
