#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "typer>=0.15.3",
#     "pydantic>=1.8.2"
# ]
# ///

from __future__ import annotations

import subprocess
import re
import os
import tempfile
import shutil
import traceback
import datetime
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich import print as rprint
from rich import box
from rich.text import Text
from pydantic import BaseModel

# --- Configuration for OS-specific rendering ---
IS_WINDOWS = os.name == "nt"
PANEL_BOX_STYLE = (
    box.ASCII if IS_WINDOWS else box.ROUNDED
)  # ROUNDED is default, ASCII is simpler for compatibility
SUCCESS_SYMBOL = "(*)" if IS_WINDOWS else "✓"
WARNING_SYMBOL = "(!)" if IS_WINDOWS else "⚠️"

# Initialize Typer app and Rich console
app = typer.Typer(
    help="Apply changes to a target branch without switching branches.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()

# State tracking - making this global for safety
WORKTREE_SHOULD_BE_KEPT = False


# --- Custom Exceptions ---
class ShellCommandError(Exception):
    """Custom exception for shell command errors, storing stderr."""

    def __init__(self, message, stderr=None):
        super().__init__(message)
        self.stderr = stderr


# Pydantic model for operation details
class PreparedOperationDetails(BaseModel):
    final_commit_message: str
    jira_id: str
    temp_worktree_dir_path: Path
    patch_file_path: Path

    class Config:
        arbitrary_types_allowed = True


# --- Helper Functions ---
def run_command(
    command: str | list[str],
    check: bool = True,
    cwd: Path | None = None,
    shell: bool = False,
) -> str:
    """
    Run a shell command and return the output.
    Raises ShellCommandError on failure if check is True.
    """
    is_shell_command_str = isinstance(command, str) or shell
    if not is_shell_command_str and not all(isinstance(arg, str) for arg in command):
        raise ValueError("Command must be a string or a list of strings.")
        
    # Safety check: when using shell=True, command must be a string
    if shell and not isinstance(command, str):
        command = " ".join(command) if isinstance(command, list) else str(command)

    try:
        result = subprocess.run(
            command,
            shell=is_shell_command_str,
            capture_output=True,
            text=True,
            check=False,
            cwd=cwd,
        )
        if check and result.returncode != 0:
            error_message = (
                f"Error executing command: {' '.join(command) if isinstance(command, list) else command}\n"
                f"Return Code: {result.returncode}\n"
                f"Stderr: {result.stderr.strip()}"
            )
            console.print(
                f"[bold red]Error executing command:[/] {' '.join(command) if isinstance(command, list) else command}"
            )
            console.print(f"[bold red]Error message:[/] {result.stderr.strip()}")
            raise ShellCommandError(error_message, stderr=result.stderr.strip())
        return result.stdout.strip()
    except FileNotFoundError:
        cmd_str = " ".join(command) if isinstance(command, list) else command
        error_message = f"Command not found: {cmd_str}. Please ensure Git (or the specified command) is installed and in your PATH."
        console.print(f"[bold red]{error_message}[/]")
        raise ShellCommandError(error_message) from None
    except Exception as e:
        cmd_str = " ".join(command) if isinstance(command, list) else command
        error_message = f"An unexpected error occurred while running '{cmd_str}': {e}"
        console.print(f"[bold red]{error_message}[/]")
        raise ShellCommandError(error_message) from e


def get_git_repo_root() -> Path:
    """Get the root directory of the current Git repository."""
    try:
        return Path(run_command(["git", "rev-parse", "--show-toplevel"]))
    except ShellCommandError:
        console.print(
            "[bold red]Error: Not a git repository or git is not installed.[/]"
        )
        raise typer.Exit(code=1)


def get_current_branch(repo_root: Path) -> str:
    """Get the name of the current branch."""
    return run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)


def extract_jira_id(text: str) -> str | None:
    """Extract JIRA ID from text (branch name or commit message).

    Common JIRA ID pattern is PROJECT-123.
    """
    pattern = r"([A-Z]+-\d+)"
    match = re.search(pattern, text)
    return match.group(1) if match else None


def get_commits_for_patch(
    diff_range_or_ref: str, target_branch_for_fallback: str, repo_root: Path
) -> list[str]:
    """Get list of commit messages for the patch using a specific diff range or ref.

    If diff_range_or_ref is a range (e.g., 'main..feature'), lists commits in that range.
    If diff_range_or_ref is a single branch/commit (less common here, as range is usually pre-calculated),
    it lists commits on that ref that are not on the target_branch_for_fallback.
    """
    try:
        # The input 'diff_range_or_ref' is expected to be the calculated range (e.g. base..source)
        # or an explicitly provided range by the user.
        commit_range_for_log = diff_range_or_ref

        console.print(
            f"[info]Fetching commit messages for effective range: '{commit_range_for_log}'[/info]"
        )
        commit_output = run_command(
            ["git", "log", "--pretty=format:%s", "--no-merges", commit_range_for_log],
            cwd=repo_root,
        )
        if not commit_output:
            # This part of the fallback might be less relevant if diff_range_or_ref is always a calculated range.
            # However, keeping it for robustness if a direct ref somehow gets through and is empty against target.
            if ".." not in diff_range_or_ref:  # If it was unexpectedly a single ref
                console.print(
                    f"[yellow]Warning:[/] No commits found with range '{commit_range_for_log}'. Trying source branch '{diff_range_or_ref}' directly against its own history relative to '{target_branch_for_fallback}'.[/yellow]"
                )
                # This specific fallback might need re-evaluation if 'target_branch_for_fallback' is always the port target.
                commit_output_fallback = run_command(
                    [
                        "git",
                        "log",
                        "--pretty=format:%s",
                        "--no-merges",
                        diff_range_or_ref,
                        f"^{target_branch_for_fallback}",
                    ],
                    cwd=repo_root,
                    check=False,
                )
                if commit_output_fallback:
                    commit_output = commit_output_fallback
                elif not commit_output:
                    console.print(
                        f"[yellow]Warning:[/] No unique commits found for source '{diff_range_or_ref}' relative to '{target_branch_for_fallback}'. The source might be behind or at the same point as the target, or it's an empty branch."
                    )
                    return []
            else:
                console.print(
                    f"[yellow]Warning:[/] No commits found for the specified range '{diff_range_or_ref}'. Ensure the range is correct and contains commits."
                )
                return []
        return commit_output.split("\n")
    except ShellCommandError as e:
        if (
            e.stderr
            and "unknown revision or path not in the working tree" in e.stderr.lower()
        ):
            console.print(
                f"[bold yellow]Warning:[/] Could not find commits. Effective source range '{diff_range_or_ref}' or target '{target_branch_for_fallback}' might be invalid or have no diff."
            )
            return []
        console.print(f"[bold red]Error getting commits for patch:[/] {e}")
        raise


# Define Enum for patch application status
class PatchApplyStatus(Enum):
    APPLIED_CLEANLY = "APPLIED_CLEANLY"
    USER_WILL_RESOLVE = "USER_WILL_RESOLVE"
    ABORTED_CONFLICT = "ABORTED_CONFLICT"
    NO_CHANGES = "NO_CHANGES"
    USING_EXTERNAL_TOOL = "USING_EXTERNAL_TOOL"


# Define Enum for supported external editors
class EditorType(Enum):
    VSCODE = "code"
    INTELLIJ = "idea"

    def command(self) -> str:
        """Return the command to run for this editor."""
        return self.value

    def display_name(self) -> str:
        """Return a user-friendly name for this editor."""
        if self == EditorType.VSCODE:
            return "VS Code"
        elif self == EditorType.INTELLIJ:
            return "IntelliJ IDEA"
        return self.value


# --- Refactored Helper Functions for apply command ---
def _resolve_source_branch(source_arg: str | None, repo_root: Path) -> str:
    if source_arg:
        console.print(f"[info]Using specified source: '{source_arg}'[/info]")
        return source_arg
    current_branch_val = get_current_branch(repo_root)
    console.print(
        f"[info]No source specified, using current branch: '{current_branch_val}'[/info]"
    )
    return current_branch_val


def _display_initial_info(
    resolved_source: str,
    base_for_diff: str,
    target_branch: str,
    repo_root: Path,
    is_range_explicit: bool,
):
    """Displays initial information about the porting operation."""
    if is_range_explicit:
        console.print(
            f"[info]Attempting to port changes from explicit range [bold cyan]{resolved_source}[/] to [bold cyan]{target_branch}[/] in repo: {repo_root}[/info]"
        )
    else:
        console.print(
            f"[info]Attempting to port changes from [bold cyan]{resolved_source}[/] (compared against base [bold yellow]{base_for_diff}[/]) to [bold cyan]{target_branch}[/] in repo: {repo_root}[/info]"
        )


def _create_patch_file(
    effective_diff_source: str, patch_file_path: Path, repo_root: Path
) -> bool:
    """Creates a patch file. Returns True if patch has content, False if empty."""
    console.print(
        f"[info]Creating patch file for effective diff source: '{effective_diff_source}'...[/info]"
    )
    run_command(
        ["git", "diff", effective_diff_source, "--output", str(patch_file_path)],
        cwd=repo_root,
    )
    if patch_file_path.stat().st_size == 0:
        console.print(
            f"[yellow]Patch file created at: {patch_file_path} is empty. No textual changes detected.[/]"
        )
        return False
    console.print(f"[info]Patch file created at: {patch_file_path}[/info]")
    return True


def _setup_worktree(
    target_branch: str, worktree_path: Path, jira_id: str, repo_root: Path
) -> str:
    """Sets up a git worktree for the target branch and creates a new branch in it."""
    console.print(
        f"[info]Setting up temporary worktree for branch '{target_branch}' at: {worktree_path}[/info]"
    )

    # Proactively remove the directory if it exists to prevent 'git worktree add' errors
    if worktree_path.exists():
        console.print(
            f"[yellow]Warning: Worktree path {worktree_path} already exists. Attempting to remove it...[/]"
        )
        try:
            shutil.rmtree(worktree_path)
            console.print(
                f"[green]{SUCCESS_SYMBOL} Successfully removed existing directory: {worktree_path}[/]"
            )
        except Exception as e:
            console.print(
                f"[bold red]Error:[/] Failed to remove existing worktree directory {worktree_path}: {e}"
            )
            console.print(
                "Please check permissions or remove it manually and try again."
            )
            raise typer.Exit(code=1)

    # Make sure target_branch exists at origin before creating worktree
    try:
        # Fetch latest from remote to ensure we have the latest branches
        run_command(
            ["git", "fetch", "origin", target_branch], cwd=repo_root, check=False
        )
    except ShellCommandError:
        console.print(
            f"[yellow]Warning: Could not fetch latest for branch '{target_branch}' from origin.[/]"
        )

    # Create the worktree - make sure to use the proper remote branch reference if needed
    if target_branch.startswith("origin/"):
        # If it's a remote branch, we need to ensure it's up to date
        branch_ref = target_branch
    else:
        # Try to use the remote branch first, fall back to local if needed
        try:
            run_command(
                ["git", "rev-parse", f"origin/{target_branch}"],
                cwd=repo_root,
                check=False,
            )
            branch_ref = f"origin/{target_branch}"
            console.print(f"[info]Using remote branch reference '{branch_ref}'[/info]")
        except ShellCommandError:
            branch_ref = target_branch
            console.print(f"[info]Using local branch reference '{branch_ref}'[/info]")

    console.print(f"[info]Creating worktree using '{branch_ref}'...[/info]")
    try:
        run_command(
            ["git", "worktree", "add", "--force", str(worktree_path), branch_ref],
            cwd=repo_root,
        )
    except ShellCommandError as e:
        console.print(f"[bold red]Failed to create worktree: {e}[/]")
        raise typer.Exit(code=1)

    # Verify the worktree was created and populated correctly
    if not worktree_path.exists():
        console.print(
            "[bold red]Error: Worktree directory was not created properly.[/]"
        )
        raise typer.Exit(code=1)

    # Check if the worktree has files in it
    files_in_worktree = list(worktree_path.glob("*"))
    if not files_in_worktree:
        console.print(
            "[bold red]Error: Worktree directory is empty. Files weren't copied.[/]"
        )
        # Try running git status to get more info
        try:
            status_output = run_command(
                ["git", "status"], cwd=worktree_path, check=False
            )
            console.print(f"[yellow]Git status in worktree: {status_output}[/]")
        except Exception:
            pass
        raise typer.Exit(code=1)

    # Always prefix with feature/ and use the jira_id and target branch
    base_branch_name = f"feature/{jira_id}-{target_branch.replace('/', '_')}"

    # Check if branch already exists locally or remotely
    branch_exists = False
    try:
        # Check if branch exists locally
        local_branch_output = run_command(
            ["git", "branch", "--list", base_branch_name], cwd=repo_root, check=False
        )
        if local_branch_output.strip():
            branch_exists = True

        # If not found locally, check if it exists remotely
        if not branch_exists:
            remote_branch_output = run_command(
                ["git", "ls-remote", "--heads", "origin", base_branch_name],
                cwd=repo_root,
                check=False,
            )
            if remote_branch_output.strip():
                branch_exists = True
    except ShellCommandError:
        # If commands fail, we'll assume the branch doesn't exist to be safe
        branch_exists = False

    new_branch_name = base_branch_name

    if branch_exists:
        console.print(
            f"[bold yellow]Warning: Branch '{base_branch_name}' already exists![/]"
        )

        choice = Prompt.ask(
            "[bold]Options:[/]\n"
            "  [cyan]1[/] - Replace existing branch (delete and recreate)\n"
            "  [cyan]2[/] - Create a new branch with unique suffix\n"
            "  [cyan]3[/] - Abort operation",
            choices=["1", "2", "3"],
            default="2",
        )

        if choice == "1":
            console.print(f"[bold]Replacing existing branch '{base_branch_name}'...[/]")
            # Delete local branch if it exists
            try:
                run_command(
                    ["git", "branch", "-D", base_branch_name],
                    cwd=repo_root,
                    check=False,
                )
            except ShellCommandError:
                # Ignore errors if the branch doesn't exist locally
                pass

            # Continue with the original branch name
            new_branch_name = base_branch_name

        elif choice == "2":
            # Create a unique branch name with timestamp
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            new_branch_name = f"{base_branch_name}-{timestamp}"
            console.print(
                f"[bold]Creating new branch with unique name: '{new_branch_name}'[/]"
            )

        else:  # choice == "3"
            console.print("[bold red]Operation aborted due to existing branch.[/]")
            # Clean up the worktree we just created
            try:
                run_command(
                    ["git", "worktree", "remove", "--force", str(worktree_path)],
                    cwd=repo_root,
                    check=False,
                )
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception:
                # Best effort cleanup
                pass
            raise typer.Exit(code=1)

    console.print(f"[info]Creating new branch '{new_branch_name}' in worktree.[/info]")

    # Use git switch -c instead of checkout for better alignment with modern git
    try:
        run_command(["git", "switch", "-c", new_branch_name], cwd=worktree_path)
    except ShellCommandError as e:
        # If branch creation fails (like if branch exists), try again with a unique name
        if "already exists" in str(e):
            console.print(
                "[yellow]Branch already exists despite our checks. Creating a unique branch name...[/]"
            )
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
            new_branch_name = f"{base_branch_name}-{timestamp}"
            console.print(
                f"[info]Trying again with unique name: '{new_branch_name}'[/info]"
            )
            run_command(["git", "switch", "-c", new_branch_name], cwd=worktree_path)
        else:
            raise

    # Verify the branch was created correctly
    current_branch = run_command(["git", "branch", "--show-current"], cwd=worktree_path)
    if current_branch.strip() != new_branch_name:
        console.print(
            f"[bold red]Error: Failed to switch to new branch. Currently on '{current_branch}'[/]"
        )
        raise typer.Exit(code=1)

    console.print(
        f"[green]{SUCCESS_SYMBOL} Successfully set up worktree with new branch '{new_branch_name}'[/]"
    )
    return new_branch_name


def _commit_and_push_changes(
    new_branch_in_worktree: str, commit_message: str, worktree_path: Path
):
    """Adds all changes, commits them, and pushes the new branch from the worktree."""
    console.print(
        f"[info]Committing changes to branch '{new_branch_in_worktree}' with message...[/info]"
    )
    run_command(["git", "add", "-A"], cwd=worktree_path)
    run_command(["git", "commit", "-m", commit_message], cwd=worktree_path)

    # Improved error handling for git push which is more prone to network failures
    console.print(
        f"[info]Pushing branch '{new_branch_in_worktree}' to remote (origin)...[/info]"
    )
    try:
        run_command(
            ["git", "push", "origin", new_branch_in_worktree], cwd=worktree_path
        )
        console.print(f"[green]{SUCCESS_SYMBOL} Successfully pushed to remote.[/]")
    except ShellCommandError as push_error:
        console.print(
            "[bold yellow]Warning:[/] Failed to push branch to remote. You can try pushing later with:[/]"
        )
        console.print(
            f"  [cyan]cd {worktree_path} && git push origin {new_branch_in_worktree}[/]"
        )
        console.print(
            f"[yellow]Push error: {push_error.stderr if hasattr(push_error, 'stderr') else str(push_error)}[/]"
        )
        if not typer.confirm("Continue anyway?", default=True):
            raise


def _open_external_editor(editor: EditorType, worktree_path: Path) -> bool:
    """Open an external editor for conflict resolution. Returns True if successful."""
    console.print(f"[info]Opening {editor.display_name()} at {worktree_path}...[/info]")

    # Always assume success to prevent worktree deletion, even if editor fails
    try:
        # Try direct command first
        cmd = [editor.command(), str(worktree_path)]
        console.print(f"[info]Executing command: {cmd}[/info]")

        try:
            run_command(cmd, check=False)
            console.print(f"[green]Successfully launched {editor.display_name()}[/]")
            return True
        except Exception as e:
            console.print(f"[yellow]Command failed: {e}[/]")

        # Show helpful instructions for manual opening
        console.print(
            f"[bold yellow]Could not automatically open {editor.display_name()}. Please open manually:[/]"
        )

        console.print(
            f"[cyan]The worktree is located at:[/] {worktree_path}\n"
            f"[cyan]1. Open {editor.display_name()} manually[/]\n"
            f"[cyan]2. Use File > Open to navigate to the worktree directory[/]"
        )

    except Exception as e:
        console.print(f"[bold red]Error trying to open editor: {e}[/]")

    # Always return True even on failure to prevent worktree deletion
    return True


def _apply_patch_and_handle_conflicts(
    patch_file_path: Path,
    worktree_path: Path,
    final_commit_message: str,
    new_branch_in_worktree: str,
    status_context=None,
) -> PatchApplyStatus:
    """Applies the patch, handles conflicts, and returns a PatchApplyStatus."""
    console.print(f"[bold]Attempting to apply patch '{patch_file_path.name}'...[/]")

    # Verify worktree exists before proceeding
    if not worktree_path.exists():
        console.print(
            "[bold red]Error: Worktree directory not found. Cannot proceed with conflict resolution.[/]"
        )
        return PatchApplyStatus.ABORTED_CONFLICT

    try:
        # First, check if the patch can be applied cleanly
        run_command(
            ["git", "apply", "--check", str(patch_file_path)], cwd=worktree_path
        )
        console.print(f"[green]{SUCCESS_SYMBOL} Patch can be applied cleanly.[/]")
        # If --check passes, apply the patch for real
        run_command(["git", "apply", str(patch_file_path)], cwd=worktree_path)
        console.print(f"[green]{SUCCESS_SYMBOL} Patch applied successfully.[/]")
        return PatchApplyStatus.APPLIED_CLEANLY
    except ShellCommandError:
        # Try to apply with 3-way merge to get conflicts into the worktree
        # This ensures the worktree is in a conflict state before showing options
        try:
            console.print(
                "[info]Attempting to apply with 3-way merge to show conflicts...[/info]"
            )
            run_command(
                ["git", "apply", "--3way", str(patch_file_path)],
                cwd=worktree_path,
                check=False,  # Don't fail if conflicts occur
            )

            # Check if we have conflicts now
            conflict_files = run_command(
                ["git", "diff", "--name-only", "--diff-filter=U"],
                cwd=worktree_path,
                check=False,
            ).strip()

            if conflict_files:
                console.print("[yellow]Conflicts detected in the following files:[/]")
                for file in conflict_files.split("\n"):
                    console.print(f"  - [cyan]{file}[/]")

        except Exception as e:
            console.print(f"[yellow]Note: Could not pre-apply conflicts: {e}[/]")

        # Pause the status indicator before showing the conflict panel
        if status_context:
            status_context.__exit__(None, None, None)

        rprint(
            Panel(
                f"[bold red]{WARNING_SYMBOL} CONFLICTS DETECTED {WARNING_SYMBOL}[/]\nThe patch cannot be applied cleanly to the target branch.",
                title="[bold red]Conflict Alert[/]",
                border_style="red",
                expand=False,
                box=PANEL_BOX_STYLE,
            )
        )

        # Create a more appealing menu with better descriptions
        console.print("\n[bold]Please select how you want to handle the conflicts:[/]")
        
        options = [
            (
                "1",
                "Apply with reject files",
                "Creates .rej files for conflicts that you can review later",
            ),
            (
                "2",
                "Apply with 3-way merge",
                "Uses Git's 3-way merge to show conflicts directly in files",
            ),
            (
                "3",
                "Open in VS Code",
                "Attempt to open VS Code with the worktree for resolving conflicts",
            ),
            (
                "4",
                "Open in IntelliJ IDEA",
                "Attempt to open IntelliJ with the worktree for resolving conflicts",
            ),
            ("5", "Abort operation", "Cancel the operation completely"),
        ]

        for opt, title, desc in options:
            console.print(f"  [cyan]{opt}[/] - [bold]{title}[/]: {desc}")

        choice = Prompt.ask(
            "\n[bold]Choose an option[/]",
            choices=["1", "2", "3", "4", "5"],
            default="2",
        )

        # Show confirmation of selection
        choice_descriptions = {opt: title for opt, title, _ in options}
        console.print(f"[bold green]Selected: {choice_descriptions[choice]}[/]")

        guidance_message = (
            f"Please navigate to [cyan]{worktree_path}[/] to resolve conflicts manually.\n"
            f"After resolving, run:\n"
            f"  [cyan]git add .[/]\n"
            f'  [cyan]git commit -m "{final_commit_message[:70].replace('"', "")}..."[/] (use full message)\n'
            f"  [cyan]git push origin {new_branch_in_worktree}[/]\n\n"
            f"Worktree remains at [cyan]{worktree_path}[/]. Remove it later with:\n"
            f"[cyan]git worktree remove --force {worktree_path}[/]"
        )

        if choice == "1":
            console.print("[bold]Applying patch with --reject option...[/]")
            run_command(
                ["git", "apply", "--reject", str(patch_file_path)], cwd=worktree_path
            )
            rprint(
                Panel(
                    f"[yellow]Patch applied with conflicts saved in [bold].rej[/] files.[/]\n{guidance_message}",
                    title="[bold yellow]Manual Resolution Required[/]",
                    border_style="yellow",
                    box=PANEL_BOX_STYLE,
                )
            )
            return PatchApplyStatus.USER_WILL_RESOLVE
        elif choice == "2":
            console.print("[bold]Applying patch with --3way merge option...[/]")
            try:
                # We may have already applied it above in the pre-check, but run again to be sure
                run_command(
                    ["git", "apply", "--3way", str(patch_file_path)], cwd=worktree_path
                )
                # Check if we still have conflicts
                has_conflicts = False
                try:
                    result = run_command(
                        ["git", "diff", "--name-only", "--diff-filter=U"],
                        cwd=worktree_path,
                        check=False,
                    )
                    conflicted_files = (
                        result.strip().split("\n") if result.strip() else []
                    )
                    has_conflicts = bool(conflicted_files)

                    if has_conflicts:
                        console.print(
                            "[bold yellow]Conflicts detected after 3-way merge:[/]"
                        )
                        for file in conflicted_files:
                            console.print(f"  - [cyan]{file}[/]")
                except ShellCommandError:
                    # If the command fails, assume there are conflicts
                    has_conflicts = True

                if has_conflicts:
                    rprint(
                        Panel(
                            f"[yellow]Merge conflicts still present after 3-way merge.[/]\n{guidance_message}",
                            title="[bold yellow]Manual Resolution Required[/]",
                            border_style="yellow",
                            box=PANEL_BOX_STYLE,
                        )
                    )
                else:
                    console.print("[green]3-way merge succeeded without conflicts![/]")

                return PatchApplyStatus.USER_WILL_RESOLVE
            except ShellCommandError as e:
                console.print(f"[bold red]3-way merge failed: {e}[/]")
                rprint(
                    Panel(
                        f"[bold red]3-way merge failed.[/]\n{guidance_message}",
                        title="[bold red]Merge Failed[/]",
                        border_style="red",
                        box=PANEL_BOX_STYLE,
                    )
                )
                return PatchApplyStatus.USER_WILL_RESOLVE
        elif choice == "3":
            # Open VS Code
            console.print(
                f"[bold]Attempting to open VS Code for conflicts in worktree:[/] {worktree_path}"
            )
            # Flag that we want to keep the worktree regardless of what happens next
            global WORKTREE_SHOULD_BE_KEPT
            WORKTREE_SHOULD_BE_KEPT = True

            # Verify worktree still exists
            if not worktree_path.exists():
                console.print(
                    "[bold red]Error: Worktree directory no longer exists![/]"
                )
                return PatchApplyStatus.ABORTED_CONFLICT

            if _open_external_editor(EditorType.VSCODE, worktree_path):
                rprint(
                    Panel(
                        f"[cyan]VS Code has been opened for conflict resolution.[/]\n{guidance_message}",
                        title="[bold cyan]VS Code Integration[/]",
                        border_style="cyan",
                        box=PANEL_BOX_STYLE,
                    )
                )
            else:
                # If opening failed, still show the guidance
                rprint(
                    Panel(
                        f"[yellow]Couldn't open VS Code automatically. Please open the worktree manually at:[/]\n[bold cyan]{worktree_path}[/]\n\n{guidance_message}",
                        title="[bold yellow]Manual Opening Required[/]",
                        border_style="yellow",
                        box=PANEL_BOX_STYLE,
                    )
                )
            return PatchApplyStatus.USER_WILL_RESOLVE
        elif choice == "4":
            # Open IntelliJ IDEA
            console.print(
                f"[bold]Attempting to open IntelliJ IDEA for conflicts in worktree:[/] {worktree_path}"
            )
            # Flag that we want to keep the worktree regardless of what happens next
            global WORKTREE_SHOULD_BE_KEPT
            WORKTREE_SHOULD_BE_KEPT = True

            # Verify worktree still exists
            if not worktree_path.exists():
                console.print(
                    "[bold red]Error: Worktree directory no longer exists![/]"
                )
                return PatchApplyStatus.ABORTED_CONFLICT

            if _open_external_editor(EditorType.INTELLIJ, worktree_path):
                rprint(
                    Panel(
                        f"[cyan]IntelliJ IDEA has been opened for conflict resolution.[/]\n{guidance_message}",
                        title="[bold cyan]IntelliJ IDEA Integration[/]",
                        border_style="cyan",
                        box=PANEL_BOX_STYLE,
                    )
                )
            else:
                # If opening failed, still show the guidance
                rprint(
                    Panel(
                        f"[yellow]Couldn't open IntelliJ IDEA automatically. Please open the worktree manually at:[/]\n[bold cyan]{worktree_path}[/]\n\n{guidance_message}",
                        title="[bold yellow]Manual Opening Required[/]",
                        border_style="yellow",
                        box=PANEL_BOX_STYLE,
                    )
                )
            # Return USER_WILL_RESOLVE instead of USING_EXTERNAL_TOOL to ensure proper cleanup logic
            return PatchApplyStatus.USER_WILL_RESOLVE
        else:
            console.print("[bold red]Operation aborted due to conflicts.[/]")
            return PatchApplyStatus.ABORTED_CONFLICT
    except Exception:  # No need to name the exception if we're not using it
        # Handle any exceptions while processing
        if status_context:
            try:
                status_context.__exit__(None, None, None)
            except Exception:
                pass
        raise  # Re-raise the exception to be caught by the outer handlers


def _prepare_operation_details(
    original_source_ref_name: str,
    effective_diff_source: str,
    target_branch: str,
    message_override: str | None,
    repo_root: Path,
) -> PreparedOperationDetails:
    """Prepares JIRA ID, commit message, and temporary file paths, returning a Pydantic model."""
    jira_id: str | None = None

    # 1. Attempt to extract JIRA ID from the original source_ref_name string (e.g., branch name)
    console.print(
        f"[bold]Attempting to extract JIRA ID from original source ref name: '{original_source_ref_name}'...[/]"
    )
    jira_id = extract_jira_id(original_source_ref_name)
    if jira_id:
        console.print(
            f"[green]{SUCCESS_SYMBOL} Found JIRA ID in original source ref name:[/] {jira_id}"
        )

    # 2. If not found, attempt from commit messages of the patch (using effective_diff_source)
    if not jira_id:
        console.print(
            f"[bold]Attempting to extract JIRA ID from commits in effective diff source: '{effective_diff_source}'...[/]"
        )
        # Pass target_branch for fallback logic within get_commits_for_patch, though less critical if effective_diff_source is usually a range
        commits_for_jira = get_commits_for_patch(
            effective_diff_source, target_branch, repo_root
        )
        for commit_msg in commits_for_jira:
            jira_id = extract_jira_id(commit_msg)
            if jira_id:
                console.print(
                    f"[green]{SUCCESS_SYMBOL} Found JIRA ID in commit message '[{commit_msg[:50]}...]':[/] {jira_id}"
                )
                break

    # 3. If still not found, attempt from target_branch name
    if not jira_id:
        console.print(
            f"[bold]Attempting to extract JIRA ID from target branch name: '{target_branch}'...[/]"
        )
        jira_id = extract_jira_id(target_branch)
        if jira_id:
            console.print(
                f"[green]{SUCCESS_SYMBOL} Found JIRA ID in target branch name:[/] {jira_id}"
            )

    # 4. Error if no JIRA ID is found
    if not jira_id:
        console.print(
            "[bold red]Error:[/] Could not determine JIRA ID from source, patch commits, or target branch name."
        )
        console.print(
            "Please ensure the JIRA ID is present or provide a full commit message with -m."
        )
        raise typer.Exit(code=1)

    # Get commit messages for the final commit body, using effective_diff_source
    commits_for_final_msg = get_commits_for_patch(
        effective_diff_source, target_branch, repo_root
    )
    commit_list_str = (
        "\n".join([f"- {c}" for c in commits_for_final_msg])
        if commits_for_final_msg
        else "No individual commits (changes are uncommitted or patch base is HEAD)."
    )

    final_commit_message = message_override or (
        f"{jira_id}: Apply changes from '{original_source_ref_name}' to '{target_branch}'\n\n"
        f"This commit squashes the following changes:\n{commit_list_str}"
    )

    # Path for the worktree itself. This directory will be created by mkdtemp.
    # _setup_worktree will clean it up if it exists and then git worktree add will use/recreate it.
    temp_worktree_dir_path = Path(
        tempfile.mkdtemp(
            prefix="git-port-wt-", suffix=f"-{target_branch.replace('/', '_')}"
        )
    )

    # Patch file is created as an independent temporary file.
    # We use delete=False because its name is passed around and it's explicitly cleaned up.
    # It's created in the repo_root for easier inspection if needed during manual conflict resolution.
    patch_temp_file = tempfile.NamedTemporaryFile(
        delete=False, suffix=".diff", prefix=f"patch-{jira_id}-", dir=repo_root
    )
    patch_file_path = Path(patch_temp_file.name)
    patch_temp_file.close()  # File is created, but empty. _create_patch_file will populate it.

    return PreparedOperationDetails(
        final_commit_message=final_commit_message,
        jira_id=jira_id,
        temp_worktree_dir_path=temp_worktree_dir_path,
        patch_file_path=patch_file_path,
    )


def _cleanup_worktree(worktree_path: Path, repo_root: Path) -> None:
    """Forcefully remove the git worktree."""
    console.print(f"[info]Cleaning up worktree at: {worktree_path}[/info]")
    try:
        # Ensure CWD is repo_root for git commands, though git worktree remove might be less sensitive to CWD
        # The primary concern is that the worktree path itself isn't the CWD.
        if Path.cwd() == worktree_path:
            os.chdir(repo_root)
        run_command(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_root,
            check=True,
        )
        console.print(
            f"[green]{SUCCESS_SYMBOL} Successfully removed worktree registration: {worktree_path}[/]"
        )
        # git worktree remove --force should also remove the directory.
        # If it's still there (e.g., permissions, or unexpected files), shutil.rmtree later will try.
    except ShellCommandError as e:
        console.print(
            f"[bold yellow]Warning:[/] 'git worktree remove' failed for {worktree_path}. Git command stderr: {e.stderr}[/]"
        )
        console.print(
            f"You may need to remove it manually: git worktree remove --force {worktree_path}"
        )
    except Exception as e:
        console.print(
            f"[bold yellow]Warning:[/] Unexpected error removing worktree {worktree_path}: {e}[/]"
        )
        console.print(
            f"You may need to remove it manually: git worktree remove --force {worktree_path}"
        )


@app.command()
def apply(
    target: str = typer.Argument(..., help="Target branch (e.g., 'main')"),
    message: str | None = typer.Option(
        None, "-m", "--message", help="Custom commit message."
    ),
    source: str | None = typer.Option(
        None,
        "-s",
        "--source",
        help="Source branch/commit/range (e.g., 'origin/develop', 'HEAD~3', 'A..B'). Defaults to current branch.",
    ),
    base: str = typer.Option(
        "origin/develop",
        "--base",
        help="Base for diff if source isn't a range. Default: 'origin/develop'.",
    ),
) -> None:
    """
    Apply changes from a source (branch/commit/range) to a target branch.

    This command automates the process of creating a patch from the source,
    setting up a temporary worktree for the target branch, applying the patch,
    and then committing and pushing the changes to a new branch on the remote.
    It's designed to simplify porting changes without manual branch switching and patch handling.

    If a JIRA ID is found in the source branch/commit name or commit messages,
    it will be prepended to the commit message.

    Usage Examples:
    ---------------
    1. Port changes from the current branch to 'main':
       $ python scripts/git_port_to_target.py main

    2. Port changes from a specific branch ('feature/my-work') (diffed against 'origin/develop' by default) to 'develop':
       $ python scripts/git_port_to_target.py develop -s feature/my-work

    3. Port changes from current branch, but diff against 'origin/main' instead of default 'origin/develop':
       $ python scripts/git_port_to_target.py develop --base origin/main

    4. Port changes from a specific commit ('abcdef1') (diffed against 'origin/develop') to 'release/v1.2':
       $ python scripts/git_port_to_target.py release/v1.2 -s abcdef1

    5. Port an explicit commit range ('main..feature/new-stuff') to 'develop' (--base is ignored):
       $ python scripts/git_port_to_target.py develop -s main..feature/new-stuff

    6. Port changes and provide a custom commit message:
       $ python scripts/git_port_to_target.py main -m "PORT: Super important fix (JIRA-123)"

    7. Port changes from current branch (e.g., 'JIRA-456-do-something', diffed against 'origin/develop') to 'main',
       allowing JIRA ID to be inferred from current branch name:
       $ python scripts/git_port_to_target.py main
    """
    repo_root_val = get_git_repo_root()
    original_dir = Path.cwd()

    # Initialize variables for cleanup in finally block
    op_details = None
    cleanup_worktree_on_exit = False
    patch_status = None
    worktree_path = None
    keep_worktree = (
        False  # New flag to track if worktree should be kept for manual resolution
    )
    status_context = None

    try:
        resolved_source_ref_name = _resolve_source_branch(source, repo_root_val)
        is_explicit_range = ".." in resolved_source_ref_name
        effective_diff_source = (
            resolved_source_ref_name
            if is_explicit_range
            else f"{base}..{resolved_source_ref_name}"
        )

        _display_initial_info(
            resolved_source_ref_name,
            base if not is_explicit_range else "N/A (explicit range)",
            target,
            repo_root_val,
            is_explicit_range,
        )

        if (
            resolved_source_ref_name == target
        ):  # Or check against effective_diff_source's "target part"
            console.print(
                "[bold red]Error:[/] Target branch cannot be the same as the resolved source branch name."
            )
            raise typer.Exit(code=1)

        op_details = _prepare_operation_details(
            resolved_source_ref_name,
            effective_diff_source,
            target,
            message,
            repo_root_val,
        )

        # op_details now contains temp_worktree_dir_path and patch_file_path
        # These need to be referenced directly from op_details for cleanup.

        rprint(
            Panel(
                op_details.final_commit_message,
                title="[bold blue]Generated Commit Message[/]",
                border_style="blue",
                expand=False,
                box=PANEL_BOX_STYLE,
            )
        )
        if not typer.confirm(
            "Proceed with this commit message and operation?", default=True
        ):
            # Cleanup preliminarily created files if user aborts here
            if op_details.patch_file_path.exists():
                op_details.patch_file_path.unlink()
            if op_details.temp_worktree_dir_path.exists():  # Created by mkdtemp
                shutil.rmtree(op_details.temp_worktree_dir_path)
            console.print("[bold yellow]Operation aborted by user.[/]")
            raise typer.Exit()

        patch_has_content = _create_patch_file(
            effective_diff_source, op_details.patch_file_path, repo_root_val
        )

        if not patch_has_content:
            console.print(
                "[bold yellow]No textual changes detected. Nothing to apply.[/]"
            )
            # Cleanup files before exiting
            if op_details.patch_file_path.exists():
                op_details.patch_file_path.unlink()
            if op_details.temp_worktree_dir_path.exists():  # Created by mkdtemp
                shutil.rmtree(op_details.temp_worktree_dir_path)
            raise typer.Exit()

        new_branch_in_worktree = ""
        patch_status: PatchApplyStatus | None = None  # Initialize patch_status

        # Store the status context so we can pause it during conflict resolution
        status_context = None

        try:
            status_context = console.status(
                f"[bold green]Processing changes for {target}...[/]", spinner="dots"
            )
            status_context.__enter__()

            new_branch_in_worktree = _setup_worktree(
                target,
                op_details.temp_worktree_dir_path,
                op_details.jira_id,
                repo_root_val,
            )
            cleanup_worktree_on_exit = (
                True  # Mark for cleanup now that it's (git worktree) created
            )

            # Apply patch without changing current directory
            patch_status = _apply_patch_and_handle_conflicts(
                op_details.patch_file_path,
                op_details.temp_worktree_dir_path,
                op_details.final_commit_message,
                new_branch_in_worktree,
                status_context,
            )

            # Set reference to worktree path for cleanup in case of errors
            worktree_path = op_details.temp_worktree_dir_path

            match patch_status:
                case PatchApplyStatus.APPLIED_CLEANLY:
                    _commit_and_push_changes(
                        new_branch_in_worktree,
                        op_details.final_commit_message,
                        op_details.temp_worktree_dir_path,
                    )
                    rprint(
                        Panel(
                            f"[bold green]{SUCCESS_SYMBOL} Successfully applied changes and pushed to branch [cyan]{new_branch_in_worktree}[/][/]",
                            title="[bold green]Success[/]",
                            border_style="green",
                            box=PANEL_BOX_STYLE,
                        )
                    )
                case PatchApplyStatus.USER_WILL_RESOLVE:
                    # User will resolve conflicts manually, don't clean up workdir
                    cleanup_worktree_on_exit = False
                    keep_worktree = True
                    global WORKTREE_SHOULD_BE_KEPT
                    WORKTREE_SHOULD_BE_KEPT = True
                    console.print(
                        "[bold yellow]Worktree available for manual conflict resolution.[/]"
                    )
                    # Patch file is intentionally not deleted.
                    return  # Exit function, finally will run but skip worktree cleanup due to flag
                case PatchApplyStatus.ABORTED_CONFLICT:
                    console.print(
                        "[bold red]Operation aborted by user choice due to conflicts.[/]"
                    )
                    raise typer.Exit(code=1)  # finally will run and clean up worktree
        except Exception:  # No need to name the exception if we're not using it
            # Handle any exceptions while processing
            if status_context:
                try:
                    status_context.__exit__(None, None, None)
                except Exception:
                    pass
            raise  # Re-raise the exception to be caught by the outer handlers

    except ShellCommandError as e:  # Catch our custom exception from run_command
        rprint(
            Panel(
                Text(f"A shell command failed:\n{e.args[0]}", style="red"),
                title="[bold red]Shell Command Error[/]",
                border_style="red",
                box=PANEL_BOX_STYLE,
            )
        )
        console.print(
            f"[bold red]Error during operation. Worktree path: {op_details.temp_worktree_dir_path if op_details and op_details.temp_worktree_dir_path.exists() else 'Not created or already removed'}"
        )
    except (
        subprocess.CalledProcessError
    ) as e:  # Should be caught by ShellCommandError if run_command is used consistently
        rprint(
            Panel(
                Text(
                    f"A git command failed:\n{e.cmd}\nReturn Code: {e.returncode}\nOutput:\n{e.stderr}",
                    style="red",
                ),
                title="[bold red]Git Command Error[/]",
                border_style="red",
                box=PANEL_BOX_STYLE,
            )
        )
        console.print(
            f"[bold red]Error during operation. Worktree path: {op_details.temp_worktree_dir_path if op_details and op_details.temp_worktree_dir_path.exists() else 'Not created or already removed'}"
        )
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        console.print("[bold yellow]Operation interrupted by user (Ctrl+C).[/]")
    except Exception as e:
        rprint(
            Panel(
                Text(
                    f"An unexpected error occurred: {str(e)}\n{traceback.format_exc()}",
                    style="red",
                ),
                title="[bold red]Unexpected Error[/]",
                border_style="red",
                box=PANEL_BOX_STYLE,
            )
        )
        console.print(
            f"[bold red]Error during operation. Worktree path: {op_details.temp_worktree_dir_path if op_details and op_details.temp_worktree_dir_path.exists() else 'Not created or already removed'}"
        )
    finally:
        # Always ensure we return to the original directory
        if Path.cwd() != original_dir:
            os.chdir(original_dir)

        # Close the status indicator if it's still active
        if status_context:
            try:
                status_context.__exit__(None, None, None)
            except Exception:
                pass

        # Check if we have details to clean up
        if op_details is None and worktree_path is None:
            # No details, nothing to clean up
            pass
        else:
            # Prioritize the direct worktree_path reference if available
            actual_worktree_path = worktree_path or (
                op_details.temp_worktree_dir_path if op_details else None
            )

            # Use both the local and global flags to determine if we should keep the worktree
            if actual_worktree_path and not (keep_worktree or WORKTREE_SHOULD_BE_KEPT):
                # Only cleanup if we're not keeping the worktree for manual resolution
                if cleanup_worktree_on_exit and actual_worktree_path.exists():
                    _cleanup_worktree(actual_worktree_path, repo_root_val)

                # After _cleanup_worktree, the directory might still exist if 'git worktree remove' failed or left files.
                # Ensure the directory created by mkdtemp is removed.
                if actual_worktree_path.exists():
                    try:
                        shutil.rmtree(actual_worktree_path)
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: Could not fully delete worktree directory {actual_worktree_path}: {e}. Manual cleanup may be required.[/]"
                        )
            elif actual_worktree_path and (keep_worktree or WORKTREE_SHOULD_BE_KEPT):
                # If we're keeping the worktree, make sure the user knows where it is
                console.print(
                    f"[bold yellow]Leaving worktree available for manual conflict resolution at: [cyan]{actual_worktree_path}[/][/]"
                )
                console.print(
                    "[yellow]Remember to remove it manually when done with: "
                    f"[cyan]git worktree remove --force {actual_worktree_path}[/][/]"
                )

            # Cleanup patch file
            if op_details and op_details.patch_file_path.exists():
                should_delete_patch = True
                if patch_status == PatchApplyStatus.USER_WILL_RESOLVE:
                    should_delete_patch = False

                if should_delete_patch:
                    try:
                        op_details.patch_file_path.unlink()
                    except OSError as e:
                        console.print(
                            f"[yellow]Warning: Could not delete patch file {op_details.patch_file_path}: {e}[/]"
                        )
                elif (
                    patch_status == PatchApplyStatus.USER_WILL_RESOLVE
                ):  # This case means should_delete_patch was false
                    console.print(
                        f"[yellow]Patch file {op_details.patch_file_path} was not deleted due to conflicts; available for manual review.[/]"
                    )


if __name__ == "__main__":
    app()
