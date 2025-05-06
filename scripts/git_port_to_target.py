#!/usr/bin/env python3
# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "typer>=0.15.3",
#     "pydantic>=1.8.2"
# ]
# ///

import subprocess
import re
import os
import tempfile
from enum import Enum
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich import print as rprint
from pydantic import BaseModel

# Initialize Typer app and Rich console
app = typer.Typer(
    help="Apply changes to a target branch without switching branches.",
    add_completion=False,
    rich_markup_mode="rich",
)
console = Console()


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
    command: str | list[str], check: bool = True, cwd: Path | None = None
) -> str:
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


def get_commits_for_patch(source_branch: str, repo_root: Path) -> list[str]:
    """Get list of commit messages that will be included in the patch.

    Fetches commits from 'source_branch' directly.
    """
    try:
        commit_output = run_command(
            ["git", "log", "--pretty=format:%s", source_branch], cwd=repo_root
        )
        if not commit_output:
            console.print(
                "[bold yellow]Warning:[/] No commits found between source branch and HEAD."
            )
            return []
        return commit_output.split("\n")
    except ShellCommandError as e:
        if "unknown revision or path not in the working tree" in str(e.stderr).lower():
            console.print(
                f"[bold yellow]Warning:[/] Could not find commits for patch. Source branch '{source_branch}' might be invalid or have no diff with HEAD."
            )
            return []
        raise


# Define Enum for patch application status
class PatchApplyStatus(Enum):
    APPLIED_CLEANLY = "APPLIED_CLEANLY"
    USER_WILL_RESOLVE = "USER_WILL_RESOLVE"
    ABORTED_CONFLICT = "ABORTED_CONFLICT"


# --- Refactored Helper Functions for apply command ---
def _resolve_source_branch(source_arg: str | None, repo_root: Path) -> str:
    """Resolves the source branch/commit. Defaults to current branch if source_arg is None."""
    if source_arg:
        console.print(f"[info]Using specified source: '{source_arg}'[/info]")
        return source_arg
    else:
        current_branch_val = get_current_branch(repo_root)
        console.print(f"[info]No source specified, using current branch: '{current_branch_val}'[/info]")
        return current_branch_val

def _display_initial_info(resolved_source: str, target_branch: str, repo_root: Path):
    """Displays initial information about the porting operation."""
    console.print(f"[info]Attempting to port changes from [bold cyan]{resolved_source}[/] to [bold cyan]{target_branch}[/] in repo: {repo_root}[/info]")

def _create_patch_file(resolved_source: str, target_branch: str, patch_file_path: Path, repo_root: Path):
    """Creates a patch file from the resolved source against the target branch."""
    console.print(f"[info]Creating patch file for changes from '{resolved_source}' (relative to '{target_branch}')...[/info]")
    # Using target...resolved_source to get changes on resolved_source not in target
    # Ensure target branch is fetched if it's a remote tracking branch for accuracy
    # For simplicity here, assuming 'target_branch' is a locally known ref or resolvable by git diff.
    run_command(
        ["git", "diff", f"{target_branch}...{resolved_source}", "--output", str(patch_file_path)],
        cwd=repo_root
    )
    console.print(f"[info]Patch file created at: {patch_file_path}[/info]")

def _setup_worktree(target_branch: str, worktree_path: Path, jira_id: str, repo_root: Path) -> str:
    """Sets up a git worktree for the target branch and creates a new branch in it."""
    console.print(f"[info]Setting up temporary worktree for branch '{target_branch}' at: {worktree_path}[/info]")
    run_command(["git", "worktree", "add", "-f", str(worktree_path), target_branch], cwd=repo_root)
    
    new_branch_name = f"port/{jira_id}-{target_branch.replace('/', '_')}"
    console.print(f"[info]Creating and switching to new branch '{new_branch_name}' in worktree.[/info]")
    run_command(["git", "switch", "-c", new_branch_name], cwd=worktree_path)
    return new_branch_name

def _commit_and_push_changes(new_branch_in_worktree: str, commit_message: str, worktree_path: Path):
    """Adds all changes, commits them, and pushes the new branch from the worktree."""
    console.print(f"[info]Committing changes to branch '{new_branch_in_worktree}' with message...[/info]")
    run_command(["git", "add", "-A"], cwd=worktree_path)
    run_command(["git", "commit", "-m", commit_message], cwd=worktree_path)
    console.print(f"[info]Pushing branch '{new_branch_in_worktree}' to remote (origin)...[/info]")
    run_command(["git", "push", "origin", new_branch_in_worktree], cwd=worktree_path)


# --- Refactored Helper Functions for apply command (Part 2) ---
def _apply_patch_and_handle_conflicts(
    patch_file_path: Path,
    worktree_path: Path,
    final_commit_message: str,
    new_branch_in_worktree: str,
) -> PatchApplyStatus:
    """Applies the patch, handles conflicts, and returns a PatchApplyStatus. CWD must be the worktree root."""
    console.print(f"[bold]Attempting to apply patch '{patch_file_path.name}'...[/]")
    try:
        run_command(["git", "apply", "--check", str(patch_file_path)])
        console.print("[green]✓ Patch can be applied cleanly.[/]")
        run_command(["git", "apply", str(patch_file_path)])
        console.print("[green]✓ Patch applied successfully.[/]")
        return PatchApplyStatus.APPLIED_CLEANLY
    except ShellCommandError:
        rprint(
            Panel(
                "[bold red]⚠️ CONFLICTS DETECTED ⚠️[/]\nThe patch cannot be applied cleanly to the target branch.",
                title="[bold red]Conflict Alert[/]",
                border_style="red",
                expand=False,
            )
        )
        choice = Prompt.ask(
            "[bold]Options:[/]\n"
            "  [cyan]1[/] - Apply with reject files (creates .rej files for conflicts)\n"
            "  [cyan]2[/] - Apply with 3-way merge (stops for manual conflict resolution if still conflicting)\n"
            "  [cyan]3[/] - Abort operation",
            choices=["1", "2", "3"],
            default="3",
        )

        guidance_message_after_conflict = (
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
            run_command(["git", "apply", "--reject", str(patch_file_path)])
            rprint(
                Panel(
                    f"[yellow]Patch applied with conflicts saved in [bold].rej[/] files.[/]\n{guidance_message_after_conflict}",
                    title="[bold yellow]Manual Resolution Required[/]",
                    border_style="yellow",
                )
            )
            return PatchApplyStatus.USER_WILL_RESOLVE
        elif choice == "2":
            console.print("[bold]Applying patch with --3way merge option...[/]")
            run_command(["git", "apply", "--3way", str(patch_file_path)])
            rprint(
                Panel(
                    f"[yellow]Patch applied with 3-way merge attempt.[/]\n{guidance_message_after_conflict}",
                    title="[bold yellow]Manual Resolution Required[/]",
                    border_style="yellow",
                )
            )
            return PatchApplyStatus.USER_WILL_RESOLVE
        else:
            console.print("[bold red]Operation aborted due to conflicts.[/]")
            return PatchApplyStatus.ABORTED_CONFLICT


# --- Refactored Helper Functions for prepare operation details ---
def _prepare_operation_details(
    resolved_source: str,
    target_branch: str,
    message_override: str | None,
    repo_root: Path,
) -> PreparedOperationDetails:
    """Prepares JIRA ID, commit message, and temporary file paths, returning a Pydantic model."""
    jira_id: str | None = None

    # 1. Attempt to extract JIRA ID from resolved_source string
    console.print(
        f"[bold]Attempting to extract JIRA ID from resolved source string: '{resolved_source}'...[/]"
    )
    jira_id = extract_jira_id(resolved_source)
    if jira_id:
        console.print(f"[green]Found JIRA ID in resolved source string:[/] {jira_id}")

    # 2. If not found, attempt from commit messages of the patch
    if not jira_id:
        console.print(
            f"[bold]Attempting to extract JIRA ID from commits in patch source: '{resolved_source}'...[/]"
        )
        commits_for_patch = get_commits_for_patch(resolved_source, repo_root)
        for commit_msg in commits_for_patch:
            jira_id = extract_jira_id(commit_msg)
            if jira_id:
                console.print(
                    f"[green]Found JIRA ID in commit message '[{commit_msg[:50]}...]':[/] {jira_id}"
                )
                break

    # 3. If still not found, attempt from target_branch name
    if not jira_id:
        console.print(
            f"[bold]Attempting to extract JIRA ID from target branch name: '{target_branch}'...[/]"
        )
        jira_id = extract_jira_id(target_branch)
        if jira_id:
            console.print(f"[green]Found JIRA ID in target branch name:[/] {jira_id}")

    # 4. Error if no JIRA ID is found
    if not jira_id:
        console.print(
            "[bold red]Error:[/] Could not determine JIRA ID from source, patch commits, or target branch name."
        )
        console.print(
            "Please ensure the JIRA ID is present in one of these locations or provide a full commit message with -m."
        )
        raise typer.Exit(code=1)

    commits_for_message = get_commits_for_patch(resolved_source, repo_root)
    commit_list_str = (
        "\n".join([f"- {c}" for c in commits_for_message])
        if commits_for_message
        else "No individual commits (changes are uncommitted or patch base is HEAD)."
    )

    # Prepare commit message
    if message_override:
        final_commit_message = message_override
    else:
        final_commit_message = (
            f"{jira_id}: Apply changes from '{resolved_source}' to '{target_branch}'\n\n"
            f"This commit squashes the following changes:\n{commit_list_str}"
        )

    # Prepare temporary file paths
    temp_worktree_dir_path = Path(
        tempfile.mkdtemp(
            prefix="git-port-wt-", suffix=f"-{target_branch.replace('/', '_')}"
        )
    )
    patch_file_path = temp_worktree_dir_path / f"patch-{jira_id}.diff"

    return PreparedOperationDetails(
        final_commit_message=final_commit_message,
        jira_id=jira_id,
        temp_worktree_dir_path=temp_worktree_dir_path,
        patch_file_path=patch_file_path,
    )


@app.command()
def apply(
    target: str = typer.Argument(
        ..., help="Target branch to apply changes to (e.g., 'main' or 'develop')"
    ),
    message: str | None = typer.Option(
        None,
        "-m",
        "--message",
        help="Custom commit message. Overrides auto-generated message.",
    ),
    source: str | None = typer.Option(
        None,
        "-s",
        "--source",
        help="Source branch/commit to create patch from (e.g., 'origin/develop', 'HEAD~3'). Defaults to the current git branch if not specified.",
    ),
):
    """
    Apply changes from the current branch (or specified range) to a target branch
    as a single new commit, without needing to switch branches.

    It uses `git worktree` to operate on the target branch in a temporary directory.
    """
    repo_root = get_git_repo_root()
    original_dir = Path.cwd()

    patch_file_path: Path | None = None
    temp_worktree_dir_path: Path | None = None

    cleanup_worktree_on_exit = True

    try:
        resolved_source = _resolve_source_branch(source, repo_root)
        _display_initial_info(resolved_source, target, repo_root)

        if resolved_source == target:
            console.print(
                "[bold red]Error:[/] Target branch cannot be the same as the source branch."
            )
            raise typer.Exit(code=1)

        op_details = _prepare_operation_details(
            resolved_source, target, message, repo_root
        )
        final_commit_message = op_details.final_commit_message
        jira_id = op_details.jira_id
        temp_worktree_dir_path = op_details.temp_worktree_dir_path
        patch_file_path = op_details.patch_file_path

        rprint(
            Panel(
                final_commit_message,
                title="[bold blue]Generated Commit Message[/]",
                border_style="blue",
                expand=False,
            )
        )
        if not typer.confirm(
            "Proceed with this commit message and operation?", default=True
        ):
            console.print("[bold yellow]Operation aborted by user.[/]")
            raise typer.Exit()

        _create_patch_file(resolved_source, target, patch_file_path, repo_root)

        with console.status(
            f"[bold green]Processing changes for {target}...[/]", spinner="dots"
        ):
            new_branch_in_worktree = _setup_worktree(
                target, temp_worktree_dir_path, jira_id, repo_root
            )
            patch_status = _apply_patch_and_handle_conflicts(
                patch_file_path,
                temp_worktree_dir_path,
                final_commit_message,
                new_branch_in_worktree,
            )

            match patch_status:
                case PatchApplyStatus.APPLIED_CLEANLY:
                    _commit_and_push_changes(
                        new_branch_in_worktree, final_commit_message, temp_worktree_dir_path
                    )
                    rprint(
                        Panel(
                            f"[bold green]✓ Successfully applied changes and pushed to branch [cyan]{new_branch_in_worktree}[/][/]",
                            title="[bold green]Success[/]",
                            border_style="green",
                        )
                    )
                case PatchApplyStatus.USER_WILL_RESOLVE:
                    cleanup_worktree_on_exit = False
                    console.print(
                        "[bold yellow]Worktree available for manual conflict resolution.[/]"
                    )
                    return
                case PatchApplyStatus.ABORTED_CONFLICT:
                    console.print(
                        "[bold red]Operation aborted by user choice due to conflicts.[/]"
                    )
                    raise typer.Exit(code=1)

    except ShellCommandError as e:
        console.print(f"[bold red]A shell command failed during the operation:[/] {e}")
        if (
            temp_worktree_dir_path
            and temp_worktree_dir_path.exists()
            and Path.cwd() == temp_worktree_dir_path
        ):
            if typer.confirm(
                f"An error occurred. Keep worktree at '{temp_worktree_dir_path}' for manual inspection?",
                default=True,
            ):
                cleanup_worktree_on_exit = False
        raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"[bold red]An unexpected error occurred:[/] {e}")
        if (
            temp_worktree_dir_path and temp_worktree_dir_path.exists()
        ):  # Check if path was defined
            if typer.confirm(
                f"An unexpected error occurred. Keep worktree at '{temp_worktree_dir_path}' for manual inspection?",
                default=True,
            ):
                cleanup_worktree_on_exit = False
        raise typer.Exit(code=1)
    finally:
        current_cwd_before_cleanup = Path.cwd()

        if original_dir.exists() and Path.cwd() != original_dir:
            try:
                os.chdir(original_dir)
                console.print(f"Returned to original directory: {original_dir}")
            except Exception as chdir_e:
                console.print(
                    f"[bold yellow]Warning:[/] Could not return to original directory '{original_dir}'. Current CWD: '{Path.cwd()}'. Error: {chdir_e}"
                )

        if patch_file_path and patch_file_path.exists():
            try:
                patch_file_path.unlink()
                console.print(f"Cleaned up patch file: {patch_file_path.name}")
            except Exception as unlink_e:
                console.print(
                    f"[bold yellow]Warning:[/] Could not delete patch file '{patch_file_path}'. Error: {unlink_e}"
                )

        if temp_worktree_dir_path and temp_worktree_dir_path.exists():
            if cleanup_worktree_on_exit:
                console.print(
                    f"\n[dim]Cleaning up temporary worktree: {temp_worktree_dir_path}...[/]"
                )
                # Ensure CWD is not within the worktree before removal
                if (
                    current_cwd_before_cleanup.is_relative_to(temp_worktree_dir_path)
                    and original_dir.exists()
                ):
                    os.chdir(original_dir)  # Prefer original_dir if it exists
                elif (
                    current_cwd_before_cleanup.is_relative_to(temp_worktree_dir_path)
                    and repo_root.exists()
                    and not original_dir.exists()
                ):
                    os.chdir(
                        repo_root
                    )  # Fallback to repo_root if original_dir is somehow gone

                # Final check before removal if CWD is still problematic
                if Path.cwd().is_relative_to(temp_worktree_dir_path):
                    console.print(
                        f"[bold yellow]Warning:[/] Could not reliably change out of worktree directory '{temp_worktree_dir_path}'. Skipping automatic removal to prevent errors. Manual cleanup required."
                    )
                else:
                    try:
                        run_command(
                            [
                                "git",
                                "worktree",
                                "remove",
                                "--force",
                                str(temp_worktree_dir_path),
                            ],
                            cwd=repo_root,
                            check=False,
                        )
                    except ShellCommandError as e:
                        console.print(
                            f"[yellow]Warning: 'git worktree remove' command failed for {temp_worktree_dir_path}: {e.stderr or e}[/]"
                        )
                        console.print(
                            f"[yellow]Manual cleanup may be needed: rm -rf '{temp_worktree_dir_path}'[/]"
                        )
                    except Exception as e:
                        console.print(
                            f"[yellow]Warning: An unexpected error occurred during worktree cleanup for {temp_worktree_dir_path}: {e}[/]"
                        )
            else:
                console.print(
                    f"\n[bold yellow]Worktree NOT cleaned up (as per user choice or script logic):[/] {temp_worktree_dir_path}"
                )
                console.print(
                    f"[yellow]To manually clean up, run: [cyan]git worktree remove --force '{temp_worktree_dir_path}'[/] (from the main repo directory)[/]"
                )
                console.print(
                    f"[yellow]Or simply delete the directory: [cyan]rm -rf '{temp_worktree_dir_path}'[/]"
                )

        if (
            Path.cwd() != original_dir and original_dir.exists()
        ):  # Ensure final return to original_dir if possible
            os.chdir(original_dir)


if __name__ == "__main__":
    app()
