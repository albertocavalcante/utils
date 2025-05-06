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
import shutil
import traceback
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
                    f"[yellow]Warning:[/] No commits found with range '{commit_range_for_log}'. Trying source branch '{diff_range_or_ref}' directly against its own history for context (this might list more commits if target is behind or unrelated).[/yellow]"
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
            else:  # It was a specific range A..B and it's empty
                console.print(
                    f"[yellow]Warning:[/] No commits found for the specified range '{diff_range_or_ref}'. Ensure the range is correct and contains commits."
                )
                return []
        return commit_output.split("\n")
    except ShellCommandError as e:
        if "unknown revision or path not in the working tree" in str(e.stderr).lower():
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


# --- Refactored Helper Functions for apply command ---
def _resolve_source_branch(source_arg: str | None, repo_root: Path) -> str:
    """Resolves the source branch/commit. Defaults to current branch if source_arg is None."""
    if source_arg:
        console.print(f"[info]Using specified source: '{source_arg}'[/info]")
        return source_arg
    else:
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
):
    """Creates a patch file using the effective diff source (which might be a range like base..source)."""
    # effective_diff_source is already the calculated range (e.g. base..source or user_A..user_B)
    console.print(
        f"[info]Creating patch file for effective diff source: '{effective_diff_source}'...[/info]"
    )
    run_command(
        ["git", "diff", effective_diff_source, "--output", str(patch_file_path)],
        cwd=repo_root,
    )
    console.print(f"[info]Patch file created at: {patch_file_path}[/info]")


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

    run_command(
        ["git", "worktree", "add", "-f", str(worktree_path), target_branch],
        cwd=repo_root,
    )

    new_branch_name = f"port/{jira_id}-{target_branch.replace('/', '_')}"
    console.print(
        f"[info]Creating and switching to new branch '{new_branch_name}' in worktree.[/info]"
    )
    run_command(["git", "switch", "-c", new_branch_name], cwd=worktree_path)
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
    console.print(
        f"[info]Pushing branch '{new_branch_in_worktree}' to remote (origin)...[/info]"
    )
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
        rprint(
            Panel(
                f"[bold red]{WARNING_SYMBOL} CONFLICTS DETECTED {WARNING_SYMBOL}[/]\nThe patch cannot be applied cleanly to the target branch.",
                title="[bold red]Conflict Alert[/]",
                border_style="red",
                expand=False,
                box=PANEL_BOX_STYLE,
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
            run_command(
                ["git", "apply", "--reject", str(patch_file_path)], cwd=worktree_path
            )
            rprint(
                Panel(
                    f"[yellow]Patch applied with conflicts saved in [bold].rej[/] files.[/]\n{guidance_message_after_conflict}",
                    title="[bold yellow]Manual Resolution Required[/]",
                    border_style="yellow",
                    box=PANEL_BOX_STYLE,
                )
            )
            return PatchApplyStatus.USER_WILL_RESOLVE
        elif choice == "2":
            console.print("[bold]Applying patch with --3way merge option...[/]")
            run_command(
                ["git", "apply", "--3way", str(patch_file_path)], cwd=worktree_path
            )
            rprint(
                Panel(
                    f"[yellow]Patch applied with 3-way merge attempt.[/]\n{guidance_message_after_conflict}",
                    title="[bold yellow]Manual Resolution Required[/]",
                    border_style="yellow",
                    box=PANEL_BOX_STYLE,
                )
            )
            return PatchApplyStatus.USER_WILL_RESOLVE
        else:
            console.print("[bold red]Operation aborted due to conflicts.[/]")
            return PatchApplyStatus.ABORTED_CONFLICT


# --- Refactored Helper Functions for prepare operation details ---
def _prepare_operation_details(
    original_source_ref_name: str,  # e.g., 'my-feature-branch' or 'HEAD'
    effective_diff_source: str,  # e.g., 'origin/develop..my-feature-branch'
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
        commits_for_jira_extraction = get_commits_for_patch(
            effective_diff_source, target_branch, repo_root
        )
        for commit_msg in commits_for_jira_extraction:
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
            "Please ensure the JIRA ID is present in one of these locations or provide a full commit message with -m."
        )
        raise typer.Exit(code=1)

    # Get commit messages for the final commit body, using effective_diff_source
    commits_for_final_message = get_commits_for_patch(
        effective_diff_source, target_branch, repo_root
    )
    commit_list_str = (
        "\n".join([f"- {c}" for c in commits_for_final_message])
        if commits_for_final_message
        else "No individual commits (changes are uncommitted or patch base is HEAD)."
    )

    # Prepare commit message
    if message_override:
        final_commit_message = message_override
    else:
        final_commit_message = (
            f"{jira_id}: Apply changes from '{original_source_ref_name}' to '{target_branch}'\n\n"
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


def _cleanup_worktree(worktree_path: Path, repo_root: Path):
    """Forcefully removes the git worktree."""
    console.print(f"[info]Cleaning up worktree at: {worktree_path}[/info]")
    try:
        # Ensure CWD is repo_root for git commands, though git worktree remove might be less sensitive to CWD
        # The primary concern is that the worktree path itself isn't the CWD.
        if Path.cwd() == worktree_path:
            os.chdir(repo_root)  # Move out of worktree dir before removing it

        run_command(
            ["git", "worktree", "remove", "--force", str(worktree_path)],
            cwd=repo_root,
            check=True,
        )
        console.print(
            f"[green]{SUCCESS_SYMBOL} Successfully removed worktree: {worktree_path}[/]"
        )
    except ShellCommandError as e:
        console.print(
            f"[bold yellow]Warning:[/] Could not automatically remove worktree {worktree_path}. Git command failed: {e.stderr}"
        )
        console.print(
            f"Please remove it manually: git worktree remove --force {worktree_path}"
        )
    except Exception as e:
        console.print(
            f"[bold yellow]Warning:[/] An unexpected error occurred while trying to remove worktree {worktree_path}: {e}"
        )
        console.print(
            f"Please remove it manually: git worktree remove --force {worktree_path}"
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
        help="Source branch/commit to create patch from (e.g., 'origin/develop', 'HEAD~3', 'A..B'). Defaults to the current git branch if not specified.",
    ),
    base: str = typer.Option(
        "origin/develop",
        "--base",
        help="Base branch/commit to calculate the diff from, if the source is not already a range. Defaults to 'origin/develop'. Active only if --source is not a range.",
    ),
):
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
    original_dir = Path.cwd()  # Save original CWD
    os.chdir(repo_root_val)  # Ensure all git commands run from repo root

    resolved_source_ref_name = _resolve_source_branch(source, repo_root_val)

    is_explicit_range = ".." in resolved_source_ref_name

    if is_explicit_range:
        effective_diff_source = resolved_source_ref_name
        _display_initial_info(
            resolved_source_ref_name,
            "N/A (explicit range)",
            target,
            repo_root_val,
            is_explicit_range,
        )
    else:
        effective_diff_source = f"{base}..{resolved_source_ref_name}"
        _display_initial_info(
            resolved_source_ref_name, base, target, repo_root_val, is_explicit_range
        )

    if resolved_source_ref_name == target:
        console.print(
            "[bold red]Error:[/] Target branch cannot be the same as the resolved source branch name."
        )
        raise typer.Exit(code=1)

    op_details = _prepare_operation_details(
        resolved_source_ref_name, effective_diff_source, target, message, repo_root_val
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
            box=PANEL_BOX_STYLE,
        )
    )
    if not typer.confirm(
        "Proceed with this commit message and operation?", default=True
    ):
        os.chdir(original_dir)  # Restore original CWD before exiting
        console.print("[bold yellow]Operation aborted by user.[/]")
        raise typer.Exit()

    _create_patch_file(effective_diff_source, patch_file_path, repo_root_val)

    cleanup_worktree_on_exit = False
    new_branch_in_worktree = ""

    try:
        with console.status(
            f"[bold green]Processing changes for {target}...[/]", spinner="dots"
        ):
            new_branch_in_worktree = _setup_worktree(
                target, temp_worktree_dir_path, jira_id, repo_root_val
            )
            cleanup_worktree_on_exit = True  # Mark for cleanup now that it's created

            os.chdir(temp_worktree_dir_path)  # Change to worktree for patch application

            patch_status = _apply_patch_and_handle_conflicts(
                patch_file_path,
                temp_worktree_dir_path,
                final_commit_message,
                new_branch_in_worktree,
            )

            match patch_status:
                case PatchApplyStatus.APPLIED_CLEANLY:
                    _commit_and_push_changes(
                        new_branch_in_worktree,
                        final_commit_message,
                        temp_worktree_dir_path,
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

    except subprocess.CalledProcessError as e:
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
            f"[bold red]Error during operation. Worktree path: {temp_worktree_dir_path if temp_worktree_dir_path.exists() else 'Not created or already removed'}"
        )
        # Let finally block handle cleanup if worktree was created
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
            f"[bold red]Error during operation. Worktree path: {temp_worktree_dir_path if temp_worktree_dir_path.exists() else 'Not created or already removed'}"
        )
        # Let finally block handle cleanup
    finally:
        os.chdir(
            original_dir
        )  # IMPORTANT: Change back before attempting to remove worktree
        if cleanup_worktree_on_exit and temp_worktree_dir_path.exists():
            _cleanup_worktree(temp_worktree_dir_path, repo_root_val)

        # Always try to remove the patch file unless conflicts occurred and we want to keep it
        if (
            patch_file_path.exists()
            and patch_status != PatchApplyStatus.USER_WILL_RESOLVE
        ):
            try:
                patch_file_path.unlink()
                # console.print(f"[dim]Cleaned up patch file: {patch_file_path}[/]", অর্থের = True)
            except OSError as e:
                console.print(
                    f"[yellow]Warning: Could not delete patch file {patch_file_path}: {e}[/]"
                )
        elif patch_status == PatchApplyStatus.USER_WILL_RESOLVE:
            console.print(
                f"[yellow]Patch file {patch_file_path} was not deleted due to conflicts.[/]"
            )

    # Ensure CWD is restored even if typer.Exit was called earlier for user abort
    if Path.cwd() != original_dir:
        os.chdir(original_dir)


if __name__ == "__main__":
    app()
