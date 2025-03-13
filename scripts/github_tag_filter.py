#!/usr/bin/env -S uv --quiet run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests<3",
#   "packaging",
#   "rich",
#   "click",
#   "pydantic",
# ]
# ///

# type: ignore[import]
from typing import List, Dict, Any, Optional, Callable
import requests
from packaging import version
from rich.console import Console
from rich.table import Table
import click
from pydantic import BaseModel, Field, field_validator
from enum import Enum

class VersionFilterType(str, Enum):
    MAJOR_VERSION = "major_version"
    GREATER_THAN = "greater_than"
    LESS_THAN = "less_than"
    GREATER_EQUAL = "greater_equal"
    LESS_EQUAL = "less_equal"
    EXACT = "exact"
    RANGE = "range"
    ALL = "all"

class VersionFilter(BaseModel):
    name: str
    filter_type: VersionFilterType
    version_value: str
    end_version: Optional[str] = None
    
    def get_filter_function(self) -> Callable[[version.Version], bool]:
        """Generate the filter function based on the filter type and version values"""
        if self.filter_type == VersionFilterType.ALL:
            return lambda v: True
            
        if self.filter_type == VersionFilterType.MAJOR_VERSION:
            major = int(self.version_value)
            return lambda v: v.major == major
            
        elif self.filter_type == VersionFilterType.RANGE:
            start_ver = version.parse(self.version_value)
            end_ver = version.parse(self.end_version)
            return lambda v: start_ver <= v <= end_ver
            
        elif self.filter_type == VersionFilterType.GREATER_THAN:
            ver = version.parse(self.version_value)
            return lambda v: v > ver
            
        elif self.filter_type == VersionFilterType.LESS_THAN:
            ver = version.parse(self.version_value)
            return lambda v: v < ver
            
        elif self.filter_type == VersionFilterType.GREATER_EQUAL:
            ver = version.parse(self.version_value)
            return lambda v: v >= ver
            
        elif self.filter_type == VersionFilterType.LESS_EQUAL:
            ver = version.parse(self.version_value)
            return lambda v: v <= ver
            
        elif self.filter_type == VersionFilterType.EXACT:
            ver = version.parse(self.version_value)
            return lambda v: v == ver
            
        # Default case
        return lambda v: True

class GitHubCommit(BaseModel):
    sha: str
    url: str

class GitHubTag(BaseModel):
    name: str
    commit: GitHubCommit
    zipball_url: str
    tarball_url: str

class FilterResult(BaseModel):
    filter_name: str
    tags: List[GitHubTag]

def fetch_github_tags(repo_owner: str, repo_name: str) -> List[GitHubTag]:
    """
    Fetch all tags from a GitHub repository.
    
    Args:
        repo_owner: The owner of the repository
        repo_name: The name of the repository
        
    Returns:
        List of GitHubTag objects
    """
    tags_data: List[Dict[str, Any]] = []
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
            
        tags_data.extend(page_tags)
        page += 1
        
    # Convert raw data to GitHubTag models
    return [GitHubTag.model_validate(tag) for tag in tags_data]

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

def filter_tags_by_patterns(tags: List[GitHubTag], 
                           filters: List[VersionFilter]) -> Dict[str, List[GitHubTag]]:
    """
    Filter tags based on version pattern filters.
    
    Args:
        tags: List of GitHubTag objects
        filters: List of version filters to apply
        
    Returns:
        Dictionary with filter names as keys and filtered tag lists as values
    """
    results: Dict[str, List[GitHubTag]] = {}
    
    # Process each tag
    for filter_obj in filters:
        filtered_tags = []
        filter_func = filter_obj.get_filter_function()
        
        for tag in tags:
            tag_name = tag.name
            parsed_version = parse_version(tag_name)
            
            if parsed_version and filter_func(parsed_version):
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
        major = filter_expr[:-2]
        return VersionFilter(
            name=f"Version {filter_expr}",
            filter_type=VersionFilterType.MAJOR_VERSION,
            version_value=major
        )
    elif "-" in filter_expr:
        start, end = filter_expr.split("-")
        return VersionFilter(
            name=f"Version {start} to {end}",
            filter_type=VersionFilterType.RANGE,
            version_value=start,
            end_version=end
        )
    elif filter_expr.startswith(">="):
        ver = filter_expr[2:]
        return VersionFilter(
            name=f"Version >= {ver}",
            filter_type=VersionFilterType.GREATER_EQUAL,
            version_value=ver
        )
    elif filter_expr.startswith(">"):
        ver = filter_expr[1:]
        return VersionFilter(
            name=f"Version > {ver}",
            filter_type=VersionFilterType.GREATER_THAN,
            version_value=ver
        )
    elif filter_expr.startswith("<="):
        ver = filter_expr[2:]
        return VersionFilter(
            name=f"Version <= {ver}",
            filter_type=VersionFilterType.LESS_EQUAL,
            version_value=ver
        )
    elif filter_expr.startswith("<"):
        ver = filter_expr[1:]
        return VersionFilter(
            name=f"Version < {ver}",
            filter_type=VersionFilterType.LESS_THAN,
            version_value=ver
        )
    else:
        return VersionFilter(
            name=f"Version {filter_expr}",
            filter_type=VersionFilterType.EXACT,
            version_value=filter_expr
        )

class AppConfig(BaseModel):
    repo: str
    filters: List[str] = Field(default_factory=list)
    show_urls: bool = True
    
    @field_validator('repo')
    @classmethod
    def validate_repo_format(cls, v):
        if '/' not in v:
            raise ValueError("Repository must be in format 'owner/name'")
        return v
    
    def get_repo_parts(self) -> tuple[str, str]:
        owner, name = self.repo.split('/')
        return owner, name

@click.command()
@click.argument('repo', required=True)
@click.option('--filters', '-f', multiple=True, help='Version filters (e.g., "5.*", ">5.4.1", "5.0.0-6.0.0")')
@click.option('--show-urls/--no-urls', default=True, help='Show/hide tarball URLs in output')
def main(repo: str, filters: List[str], show_urls: bool) -> None:
    """
    Filter GitHub repository tags based on version patterns.
    
    REPO should be in the format "owner/name" (e.g., "bazelbuild/bazel")
    """
    console = Console()
    
    try:
        # Validate inputs using Pydantic
        config = AppConfig(repo=repo, filters=filters, show_urls=show_urls)
        repo_owner, repo_name = config.get_repo_parts()
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        return

    console.print(f"[bold]Fetching tags from GitHub repository {config.repo}...[/bold]")
    
    try:
        tags = fetch_github_tags(repo_owner, repo_name)
        console.print(f"[green]Found {len(tags)} tags.[/green]")
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {str(e)}")
        return

    # Create filters from command line arguments
    version_filters = []
    for filter_expr in config.filters:
        try:
            version_filters.append(create_version_filter(filter_expr))
        except Exception as e:
            console.print(f"[bold red]Error parsing filter '{filter_expr}':[/bold red] {str(e)}")
            return

    # If no filters specified, show all tags
    if not version_filters:
        version_filters = [VersionFilter(
            name="All versions",
            filter_type=VersionFilterType.ALL,
            version_value="*"
        )]

    # Apply filters
    filter_results = filter_tags_by_patterns(tags, version_filters)
    
    # Display results
    for filter_name, tags in filter_results.items():
        console.print(f"\n[bold green]{filter_name}[/bold green] - {len(tags)} tags found:")
        
        table = Table(show_header=True)
        table.add_column("Tag")
        table.add_column("Commit SHA")
        if config.show_urls:
            table.add_column("Tarball URL")
        
        for tag in tags:
            row = [
                tag.name,
                tag.commit.sha[:7],
            ]
            if config.show_urls:
                row.append(tag.tarball_url)
            table.add_row(*row)
        
        console.print(table)

if __name__ == "__main__":
    main()
