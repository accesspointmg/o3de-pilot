# O3DE Pilot - Git Utilities
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Utility functions for Git operations.
"""

import logging
import subprocess
import re
from functools import lru_cache
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def normalize_git_url(url: str) -> str:
    """
    Normalize a git URL for comparison and caching.
    
    Handles various git URL formats:
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo
    - git@github.com:owner/repo.git
    
    Returns:
        Normalized URL suitable for caching
    """
    if not url:
        return ""
    
    # Convert SSH URLs to HTTPS format for normalization
    if url.startswith("git@"):
        # git@github.com:owner/repo.git -> github.com/owner/repo
        match = re.match(r"git@([^:]+):(.+)", url)
        if match:
            host, path = match.groups()
            url = f"https://{host}/{path}"
    
    # Remove trailing .git if present
    if url.endswith(".git"):
        url = url[:-4]
    
    # Remove trailing slashes
    url = url.rstrip("/")
    
    return url.lower()


@lru_cache(maxsize=256)
def get_default_branch(git_url: str, timeout: float = 10.0) -> Optional[str]:
    """
    Get the default branch name for a git repository.
    
    Uses `git ls-remote --symref` to query the remote without cloning.
    Results are cached to avoid repeated network calls.
    
    Args:
        git_url: The git repository URL
        timeout: Timeout in seconds for the git command
        
    Returns:
        Branch name (e.g., "main", "master", "development") or None if failed
    """
    if not git_url:
        return None
    
    # Normalize URL for consistent caching
    normalized = normalize_git_url(git_url)
    if not normalized:
        return None
    
    # Ensure URL ends with .git for git command
    if not git_url.endswith(".git"):
        git_url = git_url + ".git"
    
    try:
        # Use git ls-remote to get the default branch reference
        # Output format: "ref: refs/heads/main\tHEAD"
        result = subprocess.run(
            ["git", "ls-remote", "--symref", git_url, "HEAD"],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode != 0:
            logger.debug(f"git ls-remote failed for {git_url}: {result.stderr}")
            return None
        
        # Parse the output to find the default branch
        # Look for line like: "ref: refs/heads/main\tHEAD"
        for line in result.stdout.splitlines():
            match = re.match(r"ref:\s+refs/heads/(\S+)\s+HEAD", line)
            if match:
                branch = match.group(1)
                logger.debug(f"Found default branch '{branch}' for {git_url}")
                return branch
        
        logger.debug(f"Could not parse default branch from ls-remote output for {git_url}")
        return None
        
    except subprocess.TimeoutExpired:
        logger.warning(f"Timeout fetching default branch for {git_url}")
        return None
    except FileNotFoundError:
        logger.warning("git command not found, cannot fetch default branch")
        return None
    except Exception as e:
        logger.debug(f"Error fetching default branch for {git_url}: {e}")
        return None


def is_git_url(url: str) -> bool:
    """
    Check if a URL is a git repository URL.
    
    Args:
        url: URL to check
        
    Returns:
        True if the URL appears to be a git repository
    """
    if not url:
        return False
    
    # SSH format
    if url.startswith("git@"):
        return True
    
    # Check for .git extension
    if url.endswith(".git"):
        return True
    
    # Check for common git hosting services
    parsed = urlparse(url)
    git_hosts = ["github.com", "gitlab.com", "bitbucket.org", "dev.azure.com"]
    for host in git_hosts:
        if host in parsed.netloc:
            return True
    
    return False


def get_local_git_remote(path: str, timeout: float = 5.0) -> Optional[str]:
    """
    Get the git remote origin URL for a local directory.
    
    Args:
        path: Path to the local directory
        timeout: Timeout in seconds for the git command
        
    Returns:
        The remote origin URL, or None if not a git repo or failed
    """
    if not path:
        return None
    
    try:
        result = subprocess.run(
            ["git", "-C", path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        return None
        
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return None


def get_local_git_upstream(path: str, timeout: float = 5.0) -> Optional[str]:
    """
    Get the git upstream remote URL for a local directory.
    
    This is useful for getting the canonical repository URL when
    working with a fork.
    
    Args:
        path: Path to the local directory
        timeout: Timeout in seconds for the git command
        
    Returns:
        The upstream remote URL, or None if not configured or failed
    """
    if not path:
        return None
    
    try:
        result = subprocess.run(
            ["git", "-C", path, "remote", "get-url", "upstream"],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        return None
        
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return None


def get_local_git_branch(path: str, timeout: float = 5.0) -> Optional[str]:
    """
    Get the current git branch for a local directory.
    
    Args:
        path: Path to the local directory
        timeout: Timeout in seconds for the git command
        
    Returns:
        The current branch name, or None if not a git repo or failed
    """
    if not path:
        return None
    
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        
        if result.returncode == 0:
            branch = result.stdout.strip()
            # HEAD is returned in detached state
            return branch if branch != "HEAD" else None
        return None
        
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return None


def is_url_cloned_locally(remote_url: str, local_repo_urls: set[str]) -> bool:
    """
    Check if a remote git URL is cloned locally.
    
    Compares the normalized remote URL against a set of normalized local repository URLs.
    
    Args:
        remote_url: The remote git repository URL to check
        local_repo_urls: Set of normalized local repository URLs
        
    Returns:
        True if the remote URL matches any local repository
    """
    if not remote_url or not local_repo_urls:
        return False
    
    normalized_remote = normalize_git_url(remote_url)
    return normalized_remote in local_repo_urls


def clear_branch_cache():
    """Clear the cached default branch lookups."""
    get_default_branch.cache_clear()


def parse_github_url(git_url: str) -> Optional[tuple[str, str]]:
    """
    Parse a GitHub URL to extract owner and repo.
    
    Args:
        git_url: GitHub repository URL (https or ssh format)
        
    Returns:
        Tuple of (owner, repo) or None if not a GitHub URL
    """
    if not git_url:
        return None
    
    # Normalize the URL
    normalized = normalize_git_url(git_url)
    if not normalized:
        return None
    
    # Parse the URL
    parsed = urlparse(normalized)
    
    # Check if it's GitHub
    if "github.com" not in parsed.netloc:
        return None
    
    # Extract path components
    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) >= 2:
        owner = path_parts[0]
        repo = path_parts[1]
        return (owner, repo)
    
    return None


@lru_cache(maxsize=128)
def get_github_releases(git_url: str, timeout: float = 10.0) -> list[str]:
    """
    Get release versions from a GitHub repository.
    
    Uses the GitHub API to fetch releases. Results are cached to avoid
    repeated network calls.
    
    Args:
        git_url: GitHub repository URL
        timeout: Timeout in seconds for the HTTP request
        
    Returns:
        List of version strings (tag names), newest first
    """
    parsed = parse_github_url(git_url)
    if not parsed:
        return []
    
    owner, repo = parsed
    
    try:
        import urllib.request
        import json
        
        # Use GitHub API to get releases
        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"
        
        request = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "O3DE-Pilot"
            }
        )
        
        with urllib.request.urlopen(request, timeout=timeout) as response:
            releases_data = json.loads(response.read().decode())
        
        # Extract tag names (versions)
        versions = []
        for release in releases_data:
            tag_name = release.get("tag_name", "")
            if tag_name:
                versions.append(tag_name)
        
        logger.debug(f"Found {len(versions)} releases for {owner}/{repo}")
        return versions
        
    except Exception as e:
        logger.debug(f"Error fetching GitHub releases for {git_url}: {e}")
        return []


def clear_releases_cache():
    """Clear the cached GitHub releases lookups."""
    get_github_releases.cache_clear()
    get_github_releases_full.cache_clear()


@lru_cache(maxsize=64)
def get_github_releases_full(git_url: str, timeout: float = 10.0) -> list[dict]:
    """
    Get full release data from a GitHub repository, including assets.

    Each returned dict contains:
        tag_name, zipball_url, tarball_url, assets (list of {name, browser_download_url})

    Args:
        git_url: GitHub repository URL
        timeout: Timeout in seconds for the HTTP request

    Returns:
        List of release dicts, newest first
    """
    parsed = parse_github_url(git_url)
    if not parsed:
        return []

    owner, repo = parsed

    try:
        import urllib.request
        import json

        api_url = f"https://api.github.com/repos/{owner}/{repo}/releases"

        request = urllib.request.Request(
            api_url,
            headers={
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "O3DE-Pilot",
            },
        )

        with urllib.request.urlopen(request, timeout=timeout) as response:
            releases_data = json.loads(response.read().decode())

        results = []
        for release in releases_data:
            tag = release.get("tag_name", "")
            if not tag:
                continue
            entry: dict = {
                "tag_name": tag,
                "zipball_url": release.get("zipball_url", ""),
                "tarball_url": release.get("tarball_url", ""),
                "assets": [
                    {
                        "name": a.get("name", ""),
                        "browser_download_url": a.get("browser_download_url", ""),
                        "digest": a.get("digest", ""),
                    }
                    for a in release.get("assets", [])
                ],
            }
            results.append(entry)

        logger.debug(f"Found {len(results)} full releases for {owner}/{repo}")
        return results

    except Exception as e:
        logger.debug(f"Error fetching full GitHub releases for {git_url}: {e}")
        return []
