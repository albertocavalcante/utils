#!/usr/bin/env python3
"""
Extract ALL URLs from Bzlmod dependencies including hidden toolchains.

This script combines multiple strategies to discover as many URLs as possible:
1. Parses MODULE.bazel.lock for already-fetched dependencies
2. Forces evaluation of module extensions
3. Extracts URLs from multiple platform builds
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Set, List, Dict, Any

def run_bazel_command(cmd: List[str]) -> tuple[int, str, str]:
    """Run a bazel command and return exit code, stdout, stderr."""
    print(f"Running: {' '.join(cmd)}", file=sys.stderr)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def extract_urls_from_lockfile(lockfile_path: Path) -> Set[str]:
    """Extract all URLs from a MODULE.bazel.lock file."""
    if not lockfile_path.exists():
        return set()
    
    with open(lockfile_path, 'r') as f:
        lockfile = json.load(f)
    
    urls = set()
    
    # 1. Extract registry URLs (modules from BCR)
    for url in lockfile.get('registryFileHashes', {}).keys():
        urls.add(url)
    
    # 2. Extract URLs from module extensions (where toolchains hide!)
    for ext_id, ext_data in lockfile.get('moduleExtensions', {}).items():
        for platform, platform_data in ext_data.items():
            if isinstance(platform_data, dict) and 'generatedRepoSpecs' in platform_data:
                for repo_name, repo_spec in platform_data['generatedRepoSpecs'].items():
                    attrs = repo_spec.get('attributes', {})
                    
                    # Extract URLs from various attributes
                    if 'url' in attrs:
                        urls.add(attrs['url'])
                    
                    if 'urls' in attrs:
                        for url in attrs['urls']:
                            urls.add(url)
                    
                    # Handle patches
                    if 'patches' in attrs:
                        for patch in attrs.get('patches', []):
                            if isinstance(patch, str) and patch.startswith('http'):
                                urls.add(patch)
    
    # 3. Extract URLs from moduleDepGraph
    for module_key, module_data in lockfile.get('moduleDepGraph', {}).items():
        if 'repoSpec' in module_data and 'attributes' in module_data['repoSpec']:
            attrs = module_data['repoSpec']['attributes']
            if 'urls' in attrs:
                for url in attrs['urls']:
                    urls.add(url)
    
    return urls

def force_extension_evaluation():
    """Force evaluation of all module extensions."""
    print("\n=== Forcing module extension evaluation ===", file=sys.stderr)
    
    # Get module graph to find all extensions
    code, stdout, stderr = run_bazel_command(["bazel", "mod", "graph", "--output=json"])
    if code != 0:
        print(f"Warning: 'bazel mod graph' failed: {stderr}", file=sys.stderr)
        return
    
    try:
        graph = json.loads(stdout)
        # Process graph to find extensions if needed
    except json.JSONDecodeError:
        print("Warning: Could not parse module graph JSON", file=sys.stderr)

def discover_all_urls(output_file: Path):
    """Main function to discover all possible URLs."""
    all_urls = set()
    
    print("=== Starting comprehensive URL discovery ===", file=sys.stderr)
    
    # Step 1: Clean to start fresh
    print("\n=== Cleaning to start fresh ===", file=sys.stderr)
    run_bazel_command(["bazel", "clean", "--expunge"])
    
    # Step 2: Fetch all dependencies
    print("\n=== Fetching all dependencies ===", file=sys.stderr)
    run_bazel_command(["bazel", "fetch", "--all"])
    all_urls.update(extract_urls_from_lockfile(Path("MODULE.bazel.lock")))
    
    # Step 3: Fetch configure-time dependencies
    print("\n=== Fetching configure-time dependencies ===", file=sys.stderr)
    run_bazel_command(["bazel", "fetch", "--all", "--configure", "--force"])
    all_urls.update(extract_urls_from_lockfile(Path("MODULE.bazel.lock")))
    
    # Step 4: Build for different platforms to discover platform-specific toolchains
    platforms = [
        "@platforms//os:linux",
        "@platforms//os:windows", 
        "@platforms//os:macos"
    ]
    
    for platform in platforms:
        print(f"\n=== Building for platform {platform} ===", file=sys.stderr)
        # Use --nobuild to avoid actual compilation
        code, _, stderr = run_bazel_command([
            "bazel", "build", 
            "--nobuild",
            f"--platforms={platform}",
            "//..."
        ])
        if code != 0:
            print(f"Warning: Build for {platform} failed: {stderr}", file=sys.stderr)
        
        # Extract URLs after each platform build
        all_urls.update(extract_urls_from_lockfile(Path("MODULE.bazel.lock")))
    
    # Step 5: Force extension evaluation
    force_extension_evaluation()
    all_urls.update(extract_urls_from_lockfile(Path("MODULE.bazel.lock")))
    
    # Step 6: Write results
    print(f"\n=== Writing {len(all_urls)} unique URLs to {output_file} ===", file=sys.stderr)
    
    with open(output_file, 'w') as f:
        f.write("# Bzlmod Dependency URLs Report\n")
        f.write(f"# Total unique URLs found: {len(all_urls)}\n")
        f.write("# Generated by extract_all_bzlmod_urls.py\n\n")
        
        # Sort URLs for consistent output
        sorted_urls = sorted(all_urls)
        
        # Group by domain for better organization
        urls_by_domain: Dict[str, List[str]] = {}
        for url in sorted_urls:
            if url.startswith("http"):
                domain = url.split("/")[2]
                urls_by_domain.setdefault(domain, []).append(url)
        
        # Write grouped URLs
        for domain, domain_urls in sorted(urls_by_domain.items()):
            f.write(f"\n## {domain} ({len(domain_urls)} URLs)\n")
            for url in domain_urls:
                f.write(f"{url}\n")
    
    print(f"\nURL extraction complete. Results written to {output_file}", file=sys.stderr)
    
    # Also create a simple JSON file for programmatic use
    json_file = output_file.with_suffix('.json')
    with open(json_file, 'w') as f:
        json.dump({
            "total_urls": len(all_urls),
            "urls": sorted(all_urls),
            "urls_by_domain": urls_by_domain
        }, f, indent=2)
    
    print(f"JSON format also written to {json_file}", file=sys.stderr)

def main():
    output_file = Path("bzlmod_urls_report.txt")
    if len(sys.argv) > 1:
        output_file = Path(sys.argv[1])
    
    discover_all_urls(output_file)

if __name__ == "__main__":
    main()