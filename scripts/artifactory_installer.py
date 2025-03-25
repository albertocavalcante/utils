#!/usr/bin/env -S uv --quiet run --script
# type: ignore[import]
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "requests<3",
#   "tqdm",
#   "pydantic>=2.0.0",
#   "rich",
#   "typer",
# ]
# ///

import os
import sys
import shutil
import tarfile
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from enum import Enum
import tempfile

import requests
from tqdm import tqdm
from pydantic import BaseModel, Field, HttpUrl, ConfigDict
import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TextColumn, BarColumn, DownloadColumn, TransferSpeedColumn, TimeRemainingColumn
from rich.table import Table
from rich.markdown import Markdown

console = Console()
app = typer.Typer(help="Download and install JFrog Artifactory OSS")

class Platform(str, Enum):
    DARWIN = "darwin"
    LINUX = "linux"
    WINDOWS = "windows"

class ArtifactoryPackage(BaseModel):
    model_config = ConfigDict(frozen=True)
    
    version: str
    platform: Platform
    size: str
    
    @property
    def filename(self) -> str:
        extension = "zip" if self.platform == Platform.WINDOWS else "tar.gz"
        return f"jfrog-artifactory-oss-{self.version}-{self.platform}.{extension}"

class ArtifactoryConfig(BaseModel):
    version: str = "7.98.17"
    base_url: str = "https://releases.jfrog.io/artifactory/bintray-artifactory/org/artifactory/oss"
    platform: Platform = Platform.DARWIN
    dest_dir: Path = Field(default_factory=lambda: Path.home() / "dev" / "tools")
    keep_archive: bool = False
    verify_checksum: bool = True
    
    @property
    def package(self) -> ArtifactoryPackage:
        # Map of platform to size (used for progress indication if content-length header is missing)
        sizes = {
            Platform.DARWIN: "1.11 GB",
            Platform.LINUX: "1.13 GB",
            Platform.WINDOWS: "1.12 GB",
        }
        
        return ArtifactoryPackage(
            version=self.version,
            platform=self.platform,
            size=sizes.get(self.platform, "Unknown")
        )
    
    @property
    def download_url(self) -> str:
        return f"{self.base_url}/jfrog-artifactory-oss/{self.version}/{self.package.filename}"
    
    @property
    def extract_path(self) -> Path:
        return self.dest_dir / f"artifactory-oss-{self.version}"
    
    @property
    def download_path(self) -> Path:
        return self.dest_dir / self.package.filename

def calculate_sha256(file_path: Path) -> str:
    """Calculate SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def download_file(url: str, local_path: Path) -> bool:
    """
    Download a file from a URL with progress bar using Rich.
    
    Args:
        url: The URL to download from
        local_path: The local path to save the file to
    
    Returns:
        bool: True if download was successful, False otherwise
    """
    # Create parent directory if it doesn't exist
    local_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Use a temporary file during download
    with tempfile.NamedTemporaryFile(delete=False) as temp_file:
        temp_path = Path(temp_file.name)
        
        try:
            with requests.get(url, stream=True) as response:
                response.raise_for_status()
                total_size = int(response.headers.get('content-length', 0))
                
                if total_size == 0:
                    console.print(f"[yellow]Warning: Content length not provided by server, progress may be inaccurate[/]")
                
                with Progress(
                    TextColumn("[bold blue]{task.description}"),
                    BarColumn(),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeRemainingColumn(),
                    console=console
                ) as progress:
                    task = progress.add_task(f"Downloading {local_path.name}", total=total_size)
                    
                    for chunk in response.iter_content(chunk_size=8192):
                        temp_file.write(chunk)
                        progress.update(task, advance=len(chunk))
            
            # Move the temp file to the final destination
            shutil.move(temp_path, local_path)
            return True
            
        except Exception as e:
            # Clean up temp file in case of error
            temp_path.unlink(missing_ok=True)
            console.print(f"[bold red]Error during download: {str(e)}[/]")
            return False

def extract_tarball(archive_path: Path, extract_to: Path) -> bool:
    """
    Extract a tarball to the specified directory.
    
    Args:
        archive_path: Path to the tarball
        extract_to: Directory to extract to
    
    Returns:
        bool: True if extraction was successful, False otherwise
    """
    # Create extraction directory if it doesn't exist
    extract_to.mkdir(parents=True, exist_ok=True)
    
    try:
        is_zip = archive_path.suffix.lower() == '.zip'
        
        with console.status(f"Reading archive information..."):
            if is_zip:
                import zipfile
                with zipfile.ZipFile(archive_path) as zip_ref:
                    members = zip_ref.namelist()
                    total = len(members)
            else:
                with tarfile.open(archive_path) as tar:
                    members = tar.getmembers()
                    total = len(members)
        
        # Determine common prefix to strip
        common_prefix: Optional[str] = None
        if total > 0:
            if is_zip:
                first_item = members[0]
                if first_item.endswith('/'):  # It's a directory
                    common_prefix = first_item
            else:
                if members[0].isdir():
                    common_prefix = members[0].name
        
        with Progress(
            TextColumn("[bold green]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=console
        ) as progress:
            task = progress.add_task(f"Extracting {archive_path.name}", total=total)
            
            if is_zip:
                import zipfile
                with zipfile.ZipFile(archive_path) as zip_ref:
                    for i, member in enumerate(members):
                        # Skip directory entries
                        if member.endswith('/'):
                            progress.update(task, advance=1)
                            continue
                            
                        # Strip common prefix if needed
                        target_path = member
                        if common_prefix and member.startswith(common_prefix):
                            target_path = member[len(common_prefix):]
                        
                        # Skip empty paths after stripping
                        if not target_path:
                            progress.update(task, advance=1)
                            continue
                        
                        # Extract the file
                        zip_ref.extract(member, path=extract_to)
                        
                        # Rename if needed
                        if common_prefix and member.startswith(common_prefix):
                            source = extract_to / member
                            target = extract_to / target_path
                            
                            # Create parent directories
                            target.parent.mkdir(parents=True, exist_ok=True)
                            
                            # Move the file
                            if source.exists():
                                source.rename(target)
                        
                        progress.update(task, advance=1)
            else:
                with tarfile.open(archive_path) as tar:
                    for i, member in enumerate(members):
                        # Strip common prefix if needed
                        if common_prefix and member.name.startswith(common_prefix):
                            member.name = member.name[len(common_prefix):]
                        
                        # Skip empty names after stripping
                        if not member.name:
                            progress.update(task, advance=1)
                            continue
                        
                        tar.extract(member, path=extract_to)
                        progress.update(task, advance=1)
        
        return True
    except Exception as e:
        console.print(f"[bold red]Error extracting archive: {str(e)}[/]")
        return False

@app.command()
def install(
    version: str = typer.Option("7.98.17", "--version", "-v", help="Artifactory version to install"),
    platform: Platform = typer.Option(Platform.DARWIN, "--platform", "-p", help="Platform to download"),
    destination: Path = typer.Option(
        None, "--dest", "-d", 
        help="Destination directory (defaults to $HOME/dev/tools)"
    ),
    keep_archive: bool = typer.Option(
        False, "--keep", "-k", 
        help="Keep the downloaded archive after extraction"
    ),
) -> None:
    """
    Download and install JFrog Artifactory OSS.
    """
    # Initialize configuration
    config = ArtifactoryConfig(
        version=version,
        platform=platform,
        dest_dir=destination or Path.home() / "dev" / "tools",
        keep_archive=keep_archive,
    )
    
    # Show information
    console.print(Panel.fit(
        f"[bold]JFrog Artifactory OSS[/bold] [cyan]{config.version}[/cyan] ([blue]{config.platform.value}[/blue])\n"
        f"Size: [yellow]{config.package.size}[/yellow]\n"
        f"Destination: [green]{config.extract_path}[/green]",
        title="Installation Details",
        border_style="bright_blue",
    ))
    
    # Confirm with user
    if not typer.confirm("Continue with installation?", default=True):
        console.print("[yellow]Installation cancelled by user[/]")
        raise typer.Exit()
    
    # Download the file if it doesn't exist
    if not config.download_path.exists():
        console.print(f"[bold blue]Downloading Artifactory OSS {config.version} for {config.platform.value}...[/]")
        if not download_file(config.download_url, config.download_path):
            console.print("[bold red]Download failed. Exiting.[/]")
            raise typer.Exit(code=1)
        console.print(f"[bold green]Download complete: {config.download_path}[/]")
    else:
        console.print(f"[bold yellow]Archive already exists: {config.download_path}[/]")
        if not typer.confirm("Use existing file?", default=True):
            console.print("[bold blue]Re-downloading file...[/]")
            if not download_file(config.download_url, config.download_path):
                console.print("[bold red]Download failed. Exiting.[/]")
                raise typer.Exit(code=1)
    
    # Extract the archive
    console.print(f"[bold blue]Extracting to {config.extract_path}...[/]")
    
    # Check if extraction directory already exists
    if config.extract_path.exists():
        if not typer.confirm(f"Directory {config.extract_path} already exists. Overwrite?", default=False):
            console.print("[yellow]Extraction cancelled by user[/]")
            if not config.keep_archive:
                console.print(f"[yellow]Keeping archive: {config.download_path}[/]")
            raise typer.Exit()
        
        # Remove existing directory
        shutil.rmtree(config.extract_path)
    
    # Extract the archive
    if not extract_tarball(config.download_path, config.extract_path):
        console.print("[bold red]Extraction failed. Exiting.[/]")
        raise typer.Exit(code=1)
    
    # Cleanup if needed
    if not config.keep_archive:
        console.print(f"[blue]Removing downloaded archive...[/]")
        config.download_path.unlink()
    
    # Show completion information
    table = Table(title="Installation Summary")
    table.add_column("Component", style="cyan")
    table.add_column("Value", style="green")
    
    table.add_row("Version", config.version)
    table.add_row("Platform", config.platform.value)
    table.add_row("Installation Path", str(config.extract_path))
    
    console.print(table)
    
    console.print(Markdown("""
    ## Next Steps
    
    1. Start Artifactory:
       ```
       cd {}
       ./bin/artifactory.sh start
       ```
    
    2. Access the web UI at: http://localhost:8081/artifactory
    
    3. Default credentials:
       - Username: admin
       - Password: password
    """.format(config.extract_path)))

@app.command()
def list_versions() -> None:
    """
    List available Artifactory versions.
    """
    console.print("[bold yellow]Fetching available versions...[/]")
    
    try:
        base_url = "https://releases.jfrog.io/artifactory/bintray-artifactory/org/artifactory/oss/jfrog-artifactory-oss/"
        response = requests.get(base_url)
        response.raise_for_status()
        
        # This is a simple approach - in reality, you'd want to parse the HTML properly
        versions = []
        for line in response.text.splitlines():
            if 'href="' in line and not line.endswith('../"'):
                version = line.split('href="')[1].split('/')[0]
                if version[0].isdigit():  # Only include numeric versions
                    versions.append(version)
        
        # Sort versions semantically
        versions.sort(key=lambda v: [int(x) for x in v.split('.')])
        
        # Display versions in a table
        table = Table(title="Available Artifactory Versions")
        table.add_column("Version", style="cyan")
        
        for version in versions[-10:]:  # Show the 10 most recent versions
            table.add_row(version)
        
        console.print(table)
        console.print(f"[blue]Showing the {min(10, len(versions))} most recent versions. Total versions: {len(versions)}[/]")
        
    except Exception as e:
        console.print(f"[bold red]Error fetching versions: {str(e)}[/]")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    app()
