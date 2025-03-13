#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests<3",
#   "packaging",
#   "rich",
# ]
# ///

from typing import List, Dict, Any, Optional, Callable
import requests
from packaging import version
from rich.console import Console
from rich.table import Table
import re
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

def display_results(filter_results: Dict[str, List[Dict[str, Any]]]) -> None:
    """
    Display the filtered results in a tabular format.
    
    Args:
        filter_results: Dictionary with filter names as keys and filtered tag lists as values
    """
    console = Console()
    
    for filter_name, tags in filter_results.items():
        console.print(f"\n[bold green]{filter_name}[/bold green] - {len(tags)} tags found:")
        
        table = Table(show_header=True)
        table.add_column("Tag")
        table.add_column("Commit SHA")
        table.add_column("Tarball URL")
        
        for tag in tags:
            table.add_row(
                tag["name"],
                tag["commit"]["sha"][:7],
                tag["tarball_url"]
            )
        
        console.print(table)

def main() -> None:
    # Fetch all tags from the repository
    repo_owner = "bazelbuild"
    repo_name = "bazel"
    
    console = Console()
    console.print("[bold]Fetching tags from GitHub...[/bold]")
    
    try:
        tags = fetch_github_tags(repo_owner, repo_name)
        console.print(f"[green]Found {len(tags)} tags.[/green]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        return
    
    # Define filters based on your requirements
    filters = [
        VersionFilter(
            name="Version 5.*",
            filter_func=lambda v: v.major == 5
        ),
        VersionFilter(
            name="Version 6.*",
            filter_func=lambda v: v.major == 6
        ),
        VersionFilter(
            name="Version > 5.4.1 and < 7.0.0",
            filter_func=lambda v: version.parse("5.4.1") < v < version.parse("7.0.0")
        ),
    ]
    
    # Apply filters
    filter_results = filter_tags_by_patterns(tags, filters)
    
    # Display results
    display_results(filter_results)
    
    # Example of adding a custom filter
    console.print("\n[bold]You can add custom filters like this:[/bold]")
    console.print("filters.append(VersionFilter(")
    console.print("    name=\"Custom filter name\",")
    console.print("    filter_func=lambda v: v.major >= 4 and v.minor >= 2")
    console.print("))")

if __name__ == "__main__":
    main()
