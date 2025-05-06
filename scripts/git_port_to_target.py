#!/usr/bin/env python3
# /// script
# requires-python = ">=3.7" # pathlib.Path and f-strings are well supported, tempfile.NamedTemporaryFile improved in 3.8+ for delete_on_close
# dependencies = [
#     "typer>=0.15.3",
# ]
# ///

import subprocess
import re
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, List, Union
import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich import print as rprint

# Initialize Typer app and Rich console
app = typer.Typer(
    help="Apply changes to a target branch without switching branches.",
    rich_markup_mode="markdown" # Enables markdown in help text
)
console = Console()

# --- Custom Exceptions ---
class ShellCommandError(Exception):
    """Custom exception for shell command errors."""
    def __init__(self, message, stderr=None):
        super().__init__(message)
        self.stderr = stderr

class JiraIDNotFoundError(Exception):
    """Custom exception when JIRA ID cannot be found."""

# --- Helper Functions ---
def run_command(command: Union[str, List[str]], check: bool = True, cwd: Optional[Path] = None) -> str:
    """
    Run a shell command and return the output.
    Raises ShellCommandError on failure if check is True.
    """
    is_shell_command_str = isinstance(command, str)
    if not is_shell_command_str and not all(isinstance(arg, str) for arg in command):
        raise ValueError("Command must be a string or a list of strings.")

    try:
        result = subprocess.run(
            command,
            shell=is_shell_command_str, # Use shell=True only if command is a string
            capture_output=True,
            text=True,
            check=False, # We'll check the returncode manually
            cwd=cwd
        )
        if check and result.returncode != 0:
            error_message = (
                f"Error executing command: {' '.join(command) if isinstance(command, list) else command}\n"
                f"Return Code: {result.returncode}\n"
                f"Stderr: {result.stderr.strip()}"
            )
            console.print(f"[bold red]Error executing command:[/] {' '.join(command) if isinstance(command, list) else command}")
            console.print(f"[bold red]Error message:[/] {result.stderr.strip()}")
            raise ShellCommandError(error_message, stderr=result.stderr.strip())
        return result.stdout.strip()
    except FileNotFoundError:
        cmd_str = ' '.join(command) if isinstance(command, list) else command
        error_message = f"Command not found: {cmd_str}. Please ensure Git (or the specified command) is installed and in your PATH."
        console.print(f"[bold red]{error_message}[/]")
        raise ShellCommandError(error_message) from None
    except Exception as e: # Catch other potential subprocess errors
        cmd_str = ' '.join(command) if isinstance(command, list) else command
        error_message = f"An unexpected error occurred while running '{cmd_str}': {e}"
        console.print(f"[bold red]{error_message}[/]")
        raise ShellCommandError(error_message) from e


def get_git_repo_root() -> Path:
    """Get the root directory of the current Git repository."""
    try:
        return Path(run_command(["git", "rev-parse", "--show-toplevel"]))
    except ShellCommandError:
        console.print("[bold red]Error: Not a git repository or git is not installed.[/]")
        raise typer.Exit(code=1)


def get_current_branch(repo_root: Path) -> str:
    """Get the name of the current branch."""
    return run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)

def extract_jira_id(text: str) -> Optional[str]:
    """Extract JIRA ID from text (branch name or commit message)."""
    # Common JIRA ID pattern: PROJECT-123
    pattern = r'([A-Z]+-\d+)'
    match = re.search(pattern, text)
    return match.group(1) if match else None

def get_jira_id_from_source(source_description: str, text_source: str, repo_root: Path) -> str:
    """Attempts to get JIRA ID, raises JiraIDNotFoundError if not found."""
    console.print(f"[bold]Attempting to extract JIRA ID from {source_description}...[/]")
    jira_id = extract_jira_id(text_source)
    if jira_id:
        console.print(f"[green]Found JIRA ID:[/] {jira_id}")
        return jira_id

    # Try from recent commit messages on the current branch
    console.print("[bold]Searching for JIRA ID in recent commits of current branch...[/]")
    # Using HEAD to get commits from the current branch.
    # If you want commits that are part of the patch specifically, this could be {source_branch}..HEAD
    commits_output = run_command(["git", "log", "--pretty=format:%s", "HEAD", "-n", "10"], cwd=repo_root) # Check last 10 commits
    if commits_output:
        for commit_msg in commits_output.split('\n'):
            jira_id = extract_jira_id(commit_msg)
            if jira_id:
                console.print(f"[green]Found JIRA ID in commit '{commit_msg}':[/] {jira_id}")
                return jira_id

    console.print("[bold red]Error:[/] No JIRA ID found.")
    console.print("[bold]Please ensure your branch name or a recent commit message contains a JIRA ID (e.g., PROJ-123).[/]")
    raise JiraIDNotFoundError("JIRA ID could not be determined.")


def get_commits_for_patch(source_branch: str, repo_root: Path) -> List[str]:
    """Get all commits that will be included in the patch."""
    try:
        commit_output = run_command(
            ["git", "log", "--pretty=format:%h %s", f"{source_branch}..HEAD"],
            cwd=repo_root
        )
        if not commit_output:
            console.print("[bold yellow]Warning:[/] No commits found between source branch and HEAD.")
            return []
        return commit_output.split('\n')
    except ShellCommandError as e:
        if "unknown revision or path not in the working tree" in str(e.stderr).lower():
            console.print(f"[bold yellow]Warning:[/] Could not find commits for patch. Source branch '{source_branch}' might be invalid or have no diff with HEAD.")
            return []
        raise # Re-raise other shell command errors


@app.command()
def apply(
    target: str = typer.Argument(..., help="Target branch to apply changes to (e.g., 'main' or 'develop')"),
    message: Optional[str] = typer.Option(None, "-m", "--message", help="Custom commit message. Overrides auto-generated message."),
    source: str = typer.Option("origin/main", "-s", "--source", help="Source branch/commit to create patch from (e.g., 'origin/develop', 'HEAD~3')."),
):
    """
    Apply changes from the current branch (or specified range) to a target branch
    as a single new commit, without needing to switch branches.

    It uses `git worktree` to operate on the target branch in a temporary directory.
    """
    repo_root = get_git_repo_root()
    original_dir = Path.cwd() # Should ideally be repo_root for git commands, but os.chdir needs absolute

    if not (repo_root / ".git").exists(): # Basic check
        console.print(f"[bold red]Error:[/] Script must be run from within a Git repository. Detected root: {repo_root}[/]")
        raise typer.Exit(code=1)

    current_branch_name = ""
    try:
        current_branch_name = get_current_branch(repo_root)
        console.print(f"[bold]Current branch:[/] {current_branch_name}")
        console.print(f"[bold]Target branch:[/] {target}")
        console.print(f"[bold]Source for patch:[/] {source}")

        jira_id = get_jira_id_from_source(f"current branch name ('{current_branch_name}') or recent commits", current_branch_name, repo_root)
    except (ShellCommandError, JiraIDNotFoundError) as e:
        console.print(f"[bold red]Initialization Error:[/] {e}")
        raise typer.Exit(code=1)

    commits_to_patch = get_commits_for_patch(source, repo_root)
    commit_list_str = "\n".join([f"- {c}" for c in commits_to_patch]) if commits_to_patch else "No individual commits (changes are uncommitted or patch base is HEAD)."

    # Define paths (use repo_root as base for consistency)
    # Place temp worktree inside .git for cleanliness or a dedicated .tmp folder at repo root
    # Using repo_root / f".{target}-temp-worktree" makes it a hidden dir at root
    temp_worktree_dir = repo_root / f".tmp-worktree-{target}-{jira_id}"
    patch_file = repo_root / f".tmp-patch-{jira_id}.patch"


    final_commit_message = ""
    if message:
        final_commit_message = message
    else:
        final_commit_message = (
            f"{jira_id}: Apply changes from '{current_branch_name}' (diff against '{source}') to '{target}'\n\n"
            f"This commit squashes the following changes:\n{commit_list_str}"
        )

    rprint(Panel(final_commit_message, title="[bold blue]Generated Commit Message[/]", border_style="blue", expand=False))
    if not typer.confirm("Proceed with this commit message and operation?", default=True):
        console.print("[bold yellow]Operation aborted by user.[/]")
        raise typer.Exit()

    try:
        with console.status(f"[bold green]Starting process to apply changes to {target}...[/]", spinner="dots"):
            console.print("[bold]Creating patch...[/]")
            patch_content = run_command(["git", "format-patch", source, "--stdout"], cwd=repo_root)
            if not patch_content:
                console.print("[bold red]Error:[/] Patch content is empty. No changes found between source and HEAD or source is invalid.")
                raise typer.Exit(code=1)
            with open(patch_file, "w", encoding='utf-8') as pf:
                pf.write(patch_content)
            console.print(f"[green]✓ Patch created:[/] {patch_file.name}")


        console.print(f"[bold]Setting up temporary worktree for '{target}' at '{temp_worktree_dir}'...[/]")
        if temp_worktree_dir.exists():
            console.print(f"[yellow]Warning:[/] Temporary worktree directory '{temp_worktree_dir}' already exists. Attempting to remove it.[/]")
            try:
                run_command(["git", "worktree", "remove", "--force", str(temp_worktree_dir)], cwd=repo_root)
            except ShellCommandError: # If it's not a valid worktree (e.g. just a dir)
                import shutil
                shutil.rmtree(temp_worktree_dir)
            console.print(f"[green]✓ Existing temporary worktree directory removed.[/]")

        run_command(["git", "worktree", "add", "--detach", str(temp_worktree_dir), target], cwd=repo_root)
        console.print(f"[green]✓ Worktree for '{target}' created.[/]")

        # Operations within the worktree
        os.chdir(temp_worktree_dir) # CRITICAL: All subsequent git commands operate here
        console.print(f"[bold]Changed directory to worktree:[/] {Path.cwd()}")

        new_branch_in_worktree = f"{target}-{jira_id}-patch"
        console.print(f"[bold]Creating branch [cyan]{new_branch_in_worktree}[/] in worktree...[/]")
        run_command(["git", "checkout", "-b", new_branch_in_worktree])
        console.print(f"[green]✓ Switched to new branch '{new_branch_in_worktree}' in worktree.[/]")

        console.print(f"[bold]Attempting to apply patch '{patch_file.name}'...[/]")
        try:
            # Check patch applicability first
            run_command(["git", "apply", "--check", str(patch_file)])
            console.print("[green]✓ Patch can be applied cleanly.[/]")
            run_command(["git", "apply", str(patch_file)])
            console.print("[green]✓ Patch applied successfully.[/]")

        except ShellCommandError: # This means `git apply --check` failed
            rprint(Panel("[bold red]⚠️ CONFLICTS DETECTED ⚠️[/]\nThe patch cannot be applied cleanly to the target branch.",
                         title="[bold red]Conflict Alert[/]", border_style="red", expand=False))

            choice = Prompt.ask(
                "[bold]Options:[/]\n"
                "  [cyan]1[/] - Apply with reject files (creates .rej files for conflicts)\n"
                "  [cyan]2[/] - Apply with 3-way merge (stops for manual conflict resolution if still conflicting)\n"
                "  [cyan]3[/] - Abort operation",
                choices=["1", "2", "3"], default="3"
            )

            if choice == "1":
                console.print("[bold]Applying patch with --reject option...[/]")
                run_command(["git", "apply", "--reject", str(patch_file)])
                rprint(Panel(
                    f"[yellow]Patch applied with conflicts saved in [bold].rej[/] files.[/]\n"
                    f"Please navigate to [cyan]{temp_worktree_dir}[/] to resolve conflicts manually.\n"
                    f"After resolving, run:\n"
                    f"  [cyan]git add .[/]\n"
                    f"  [cyan]git commit -m \"{final_commit_message[:50]}...\"[/] (use full message)\n"
                    f"  [cyan]git push origin {new_branch_in_worktree}[/]\n\n"
                    f"Worktree remains at [cyan]{temp_worktree_dir}[/]. Remove it later with:\n"
                    f"[cyan]git worktree remove {temp_worktree_dir}[/]",
                    title="[bold yellow]Manual Resolution Required[/]", border_style="yellow"
                ))
                # Do not clean up worktree here, user needs it
                return # Exit the apply function
            elif choice == "2":
                console.print("[bold]Applying patch with --3way merge option...[/]")
                run_command(["git", "apply", "--3way", str(patch_file)]) # This might still leave conflicts
                rprint(Panel(
                    f"[yellow]Patch applied with 3-way merge attempt.[/]\n"
                    f"If conflicts persist (check with `git status`), resolve them manually in [cyan]{temp_worktree_dir}[/].\n"
                    f"After resolving, run:\n"
                    f"  [cyan]git add .[/]\n"
                    f"  [cyan]git commit -m \"{final_commit_message[:50]}...\"[/] (use full message)\n"
                    f"  [cyan]git push origin {new_branch_in_worktree}[/]\n\n"
                    f"Worktree remains at [cyan]{temp_worktree_dir}[/]. Remove it later with:\n"
                    f"[cyan]git worktree remove {temp_worktree_dir}[/]",
                    title="[bold yellow]Manual Resolution Required[/]", border_style="yellow"
                ))
                # Do not clean up worktree here, user needs it
                return # Exit the apply function
            else: # choice == "3" or invalid
                console.print("[bold red]Operation aborted due to conflicts.[/]")
                raise typer.Exit(code=1) # This will trigger finally block for cleanup

        # If patch applied successfully (either directly or after user choice resolved it implicitly - unlikely for choice 1/2 here)
        console.print("[bold]Staging changes...[/]")
        run_command(["git", "add", "."])

        console.print("[bold]Committing changes...[/]")
        with tempfile.NamedTemporaryFile(mode="w+", delete=False, prefix="commit_msg_", suffix=".txt", encoding='utf-8') as tmp_f:
            tmp_f.write(final_commit_message)
            commit_msg_filepath = tmp_f.name
        try:
            run_command(["git", "commit", "-F", commit_msg_filepath])
        finally:
            Path(commit_msg_filepath).unlink(missing_ok=True) # Ensure temp commit message file is deleted

        console.print(f"[bold]Pushing branch [cyan]{new_branch_in_worktree}[/] to origin...[/]")
        run_command(["git", "push", "origin", new_branch_in_worktree])

        rprint(Panel(f"[bold green]✓ Successfully applied changes and pushed to branch [cyan]{new_branch_in_worktree}[/][/]",
                     title="[bold green]Success[/]", border_style="green"))

    except ShellCommandError as e:
        console.print(f"[bold red]A shell command failed:[/] {e}")
        if temp_worktree_dir.exists() and Path.cwd() == temp_worktree_dir:
             # Only offer to keep if error happened after chdir and worktree exists
            if typer.confirm(f"An error occurred. Keep worktree at '{temp_worktree_dir}' for manual inspection?", default=True):
                console.print(f"Worktree left at {temp_worktree_dir}. Remember to manually remove it with: git worktree remove {temp_worktree_dir}")
            else:
                # Try to clean up worktree if user doesn't want to keep it
                os.chdir(repo_root) # Go back to repo root before removing worktree
                console.print(f"Attempting to remove worktree: {temp_worktree_dir}")
                run_command(["git", "worktree", "remove", "--force", str(temp_worktree_dir)], check=False, cwd=repo_root)
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/] {e}")
        # Similar cleanup logic for unexpected errors
        if temp_worktree_dir.exists() and Path.cwd() == temp_worktree_dir:
            if typer.confirm(f"An unexpected error occurred. Keep worktree at '{temp_worktree_dir}' for manual inspection?", default=True):
                console.print(f"Worktree left at {temp_worktree_dir}. Remember to manually remove it: git worktree remove {temp_worktree_dir}")
            else:
                os.chdir(repo_root)
                console.print(f"Attempting to remove worktree: {temp_worktree_dir}")
                run_command(["git", "worktree", "remove", "--force", str(temp_worktree_dir)], check=False, cwd=repo_root)
        raise typer.Exit(code=1)
    finally:
        # Always change back to the original directory if it was changed from
        if Path.cwd() != original_dir and original_dir.exists():
            os.chdir(original_dir)
            console.print(f"Returned to original directory: {original_dir}")

        # Clean up patch file
        if patch_file.exists():
            patch_file.unlink()
            console.print(f"Cleaned up patch file: {patch_file.name}")

        # Clean up worktree if it wasn't explicitly left for manual resolution
        # This condition assumes successful path where worktree is not needed anymore
        # or if an error occurred and user chose not to keep it (handled in except blocks)
        # If apply() returns early (e.g. conflict choice 1 or 2), this finally won't remove the worktree.
        # If execution reaches here after success, we remove it.
        if 'choice' not in locals() or (locals().get('choice') == "3" and temp_worktree_dir.exists()):
             # If 'choice' is not defined (no conflict path taken or successful commit)
             # OR if user chose to abort (choice 3) during conflict (though Exit would usually be hit first)
            if temp_worktree_dir.exists() and not (
                locals().get('choice') in ["1", "2"] # Don't remove if user chose to keep for manual resolution
            ):
                # Check if we are in the worktree dir before removing
                if Path.cwd() == temp_worktree_dir:
                    os.chdir(repo_root) # Go back to repo root

                console.print(f"Cleaning up worktree: {temp_worktree_dir}")
                run_command(["git", "worktree", "remove", "--force", str(temp_worktree_dir)], check=False, cwd=repo_root) # Use check=False for cleanup

        console.print("[bold green]Done![/]")


if __name__ == "__main__":
    # Check if running in a git repository before Typer app even starts
    try:
        run_command(["git", "rev-parse", "--is-inside-work-tree"], check=True)
    except ShellCommandError:
        console.print("[bold red]Fatal Error:[/] This script must be run from within a Git repository.")
        sys.exit(1)
    except FileNotFoundError:
        console.print("[bold red]Fatal Error:[/] Git command not found. Please ensure Git is installed and in your PATH.")
        sys.exit(1)

    app()
