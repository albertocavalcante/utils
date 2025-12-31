#!/usr/bin/env -S uv run
# /// script
# dependencies = ["rich"]
# ///

import subprocess
import json
import os
import sys
from typing import List, Dict, Optional
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm
from rich.panel import Panel

# Configuration
BARE_REPO_DIR = ".bare"
MAIN_BRANCH = "main"

console = Console()

def run_command(command: List[str], cwd: str = ".") -> str:
    """Runs a shell command and returns the output as a string."""
    try:
        result = subprocess.run(
            command, cwd=cwd, capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return ""

def get_worktrees() -> List[Dict[str, Optional[str]]]:
    """Parses git worktree list using --porcelain for robustness."""
    output = run_command(["git", "--git-dir=.bare", "worktree", "list", "--porcelain"])
    worktrees = []
    if not output:
        return []

    current_wt = {}
    for line in output.splitlines():
        if line.startswith("worktree "):
            if current_wt:
                worktrees.append(current_wt)
            current_wt = {"path": line[9:].strip(), "commit": None, "branch": None}
        elif line.startswith("HEAD "):
            current_wt["commit"] = line[5:].strip()
        elif line.startswith("branch "):
            branch_ref = line[7:].strip()
            if branch_ref.startswith("refs/heads/"):
                current_wt["branch"] = branch_ref[11:]
        elif line.startswith("bare"):
            current_wt["branch"] = None # Bare repos don't have a "checked out" branch in this context
            
    if current_wt:
        worktrees.append(current_wt)
        
    return worktrees

def get_pr_status(branch: str) -> Optional[Dict]:
    """Checks GitHub PR status for a branch."""
    cwd = "main" if os.path.exists("main") else "."
    cmd = [
        "gh", "pr", "list", 
        "--head", branch, 
        "--json", "state,mergedAt,url,number,title", 
        "--state", "all",
        "--limit", "1"
    ]
    output = run_command(cmd, cwd=cwd)
    try:
        data = json.loads(output)
        return data[0] if data else None
    except json.JSONDecodeError:
        return None

def main():
    console.print(Panel.fit("🧹 [bold blue]Git Worktree Cleanup Utility[/bold blue]", border_style="blue"))
    
    if not os.path.exists(".bare") and not os.path.exists("main"):
        console.print("[bold red]Error:[/bold red] This script must be run from the root of the bare-repo worktree setup.")
        sys.exit(1)

    to_delete = []
    kept = []
    
    with console.status("[bold green]Scanning worktrees and checking PR status...", spinner="dots") as status:
        worktrees = get_worktrees()
        total_wts = len(worktrees)
        
        for i, wt in enumerate(worktrees):
            path = wt["path"]
            branch = wt["branch"]
            folder_name = os.path.basename(path)

            status.update(f"[bold green]Scanning worktrees... ({i+1}/{total_wts})[/bold green] [dim]Checking {folder_name}[/dim]")

            if path.endswith(".bare") or branch == MAIN_BRANCH or not branch:
                kept.append({"wt": wt, "reason": "Main/Bare/Detached", "pr": None})
                continue

            pr = get_pr_status(branch)
            
            if pr and pr.get("state") == "MERGED":
                to_delete.append({"wt": wt, "reason": "Merged", "pr": pr})
            elif pr and pr.get("state") == "CLOSED":
                 kept.append({"wt": wt, "reason": "Closed (Unmerged)", "pr": pr})
            elif pr:
                kept.append({"wt": wt, "reason": f"Open ({pr['state']})", "pr": pr})
            else:
                kept.append({"wt": wt, "reason": "No PR Found", "pr": None})

    table = Table(title="Worktree Analysis", show_lines=True)
    table.add_column("Path", style="dim")
    table.add_column("Branch", style="cyan")
    table.add_column("PR Status", style="magenta")
    table.add_column("Action", justify="center")

    all_results = to_delete + kept
    all_results.sort(key=lambda x: (x not in to_delete, x['wt']['path']))
    
    for item in all_results:
        wt = item['wt']
        path_name = os.path.basename(wt['path'])
        branch_name = wt['branch'] or "[dim]N/A[/dim]"
        pr = item['pr']
        
        if pr:
            pr_text = f"[link={pr['url']}]#{pr['number']}[/link] {pr['state']}"
            title_text = f"\n[dim]{pr['title']}[/dim]"
        else:
            pr_text = "[dim]-"
            title_text = ""

        if item in to_delete:
            action = "[bold red]DELETE[/bold red]"
            path_display = f"[red]{path_name}[/red]"
        else:
            action = "[green]KEEP[/green]"
            path_display = path_name

        table.add_row(path_display, branch_name, pr_text + title_text, action)

    console.print(table)

    if not to_delete:
        console.print("\n[bold green]✨ Everything is clean! No worktrees to delete.[/bold green]")
        return

    console.print(f"\n[bold]Found [red]{len(to_delete)}[/red] worktrees that can be safely removed.[/bold]")
    
    should_delete = "--force" in sys.argv or Confirm.ask("Do you want to proceed with deletion?")

    if should_delete:
        console.print()
        for item in to_delete:
            wt = item['wt']
            path = wt['path']
            branch = wt['branch']
            
            console.print(f"🗑️  Deleting [red]{os.path.basename(path)}[/red]...")
            run_command(["git", "--git-dir=.bare", "worktree", "remove", path, "--force"])
            if branch:
                run_command(["git", "-C", "main", "branch", "-D", branch])
                
        console.print("\n[bold green]✅ Cleanup complete![/bold green]")
    else:
        console.print("\n[yellow]Operation cancelled.[/yellow]")

if __name__ == "__main__":
    main()
