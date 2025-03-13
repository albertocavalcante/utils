#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests<3",
#   "packaging",
#   "rich",
#   "click",
# ]
# ///

from typing import List, Dict, Any, Optional, Callable
import requests
from packaging import version
from rich.console import Console
from rich.table import Table
import click
from dataclasses import dataclass

@dataclass
class VersionFilter:
    name: str
    filter_func: Callable[[version.Version], bool]

def fetch_github_tags(repo_owner: str, repo_name: str) -> List[Dict[str, Any]]:
    """
    Fetch all tags from a GitHub repository.
    
    Args:
        repo_owner: The owner of the repository
        repo_name: The name of the repository
        
    Returns:
        List of tag objects from the GitHub API
    """
    tags: List[Dict[str, Any]] = []
    page = 1
    per_page = 100
    
    while True:
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/tags?page={page}&per_page={per_page}"
        response = requests.get(url)
        
        if response.status_code != 200:
            raise Exception(f"Failed to fetch tags: {response.status_code} {response.text}")
        
        page_tags = response.json()
        if not page_tags:
            break
            
        tags.extend(page_tags)
        page += 1
        
    return tags

def parse_version(tag_name: str) -> Optional[version.Version]:
    """
    Parse a tag name into a version object.
    
    Args:
        tag_name: The name of the tag
        
    Returns:
        A Version object or None if the tag doesn't represent a version
    """
    # Remove 'v' prefix if present
    if tag_name.startswith("v"):
        tag_name = tag_name[1:]
    
    try:
        return version.parse(tag_name)
    except (version.InvalidVersion, TypeError):
        return None

def filter_tags_by_patterns(tags: List[Dict[str, Any]], 
                           filters: List[VersionFilter]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Filter tags based on version pattern filters.
    
    Args:
        tags: List of tag objects from the GitHub API
        filters: List of version filters to apply
        
    Returns:
        Dictionary with filter names as keys and filtered tag lists as values
    """
    results: Dict[str, List[Dict[str, Any]]] = {}
    
    # Process each tag
    for filter_obj in filters:
        filtered_tags = []
        
        for tag in tags:
            tag_name = tag["name"]
            parsed_version = parse_version(tag_name)
            
            if parsed_version and filter_obj.filter_func(parsed_version):
                filtered_tags.append(tag)
        
        results[filter_obj.name] = filtered_tags
    
    return results

def create_version_filter(filter_expr: str) -> VersionFilter:
    """
    Create a VersionFilter from a string expression.
    
    Supported formats:
    - "X.*" : Match major version X
    - ">X.Y.Z" : Greater than version X.Y.Z
    - "<X.Y.Z" : Less than version X.Y.Z
    - ">=X.Y.Z" : Greater than or equal to version X.Y.Z
    - "<=X.Y.Z" : Less than or equal to version X.Y.Z
    - "X.Y.Z-A.B.C" : Range between X.Y.Z (inclusive) and A.B.C (inclusive)
    """
    if filter_expr.endswith(".*"):
        major = int(filter_expr[:-2])
        return VersionFilter(
            name=f"Version {filter_expr}",
            filter_func=lambda v: v.major == major
        )
    elif "-" in filter_expr:
        start, end = filter_expr.split("-")
        start_ver = version.parse(start)
        end_ver = version.parse(end)
        return VersionFilter(
            name=f"Version {start} to {end}",
            filter_func=lambda v: start_ver <= v <= end_ver
        )
    elif filter_expr.startswith(">"):
        if filter_expr.startswith(">="):
            ver = version.parse(filter_expr[2:])
            return VersionFilter(
                name=f"Version >= {ver}",
                filter_func=lambda v: v >= ver
            )
        ver = version.parse(filter_expr[1:])
        return VersionFilter(
            name=f"Version > {ver}",
            filter_func=lambda v: v > ver
        )
    elif filter_expr.startswith("<"):
        if filter_expr.startswith("<="):
            ver = version.parse(filter_expr[2:])
            return VersionFilter(
                name=f"Version <= {ver}",
                filter_func=lambda v: v <= ver
            )
        ver = version.parse(filter_expr[1:])
        return VersionFilter(
            name=f"Version < {ver}",
            filter_func=lambda v: v < ver
        )
    else:
        ver = version.parse(filter_expr)
        return VersionFilter(
            name=f"Version {ver}",
            filter_func=lambda v: v == ver
        )

@click.command()
@click.argument('repo', required=True)
@click.option('--filters', '-f', multiple=True, help='Version filters (e.g., "5.*", ">5.4.1", "5.0.0-6.0.0")')
@click.option('--show-urls/--no-urls', default=True, help='Show/hide tarball URLs in output')
def main(repo: str, filters: List[str], show_urls: bool) -> None:
    """
    Filter GitHub repository tags based on version patterns.
    
    REPO should be in the format "owner/name" (e.g., "bazelbuild/bazel")
    """
    try:
        repo_owner, repo_name = repo.split('/')
    except ValueError:
        console = Console()
        console.print("[bold red]Error:[/bold red] Repository must be in format 'owner/name'")
        return

    console = Console()
    console.print(f"[bold]Fetching tags from GitHub repository {repo}...[/bold]")
    
    try:
        tags = fetch_github_tags(repo_owner, repo_name)
        console.print(f"[green]Found {len(tags)} tags.[/green]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        return

    # Create filters from command line arguments
    version_filters = []
    for filter_expr in filters:
        try:
            version_filters.append(create_version_filter(filter_expr))
        except Exception as e:
            console.print(f"[bold red]Error parsing filter '{filter_expr}':[/bold red] {str(e)}")
            return

    # If no filters specified, show all tags
    if not version_filters:
        version_filters = [VersionFilter(
            name="All versions",
            filter_func=lambda v: True
        )]

    # Apply filters
    filter_results = filter_tags_by_patterns(tags, version_filters)
    
    # Display results
    for filter_name, tags in filter_results.items():
        console.print(f"\n[bold green]{filter_name}[/bold green] - {len(tags)} tags found:")
        
        table = Table(show_header=True)
        table.add_column("Tag")
        table.add_column("Commit SHA")
        if show_urls:
            table.add_column("Tarball URL")
        
        for tag in tags:
            row = [
                tag["name"],
                tag["commit"]["sha"][:7],
            ]
            if show_urls:
                row.append(tag["tarball_url"])
            table.add_row(*row)
        
        console.print(table)

if __name__ == "__main__":
    main()
