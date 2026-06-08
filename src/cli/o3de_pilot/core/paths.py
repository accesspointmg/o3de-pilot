# O3DE Pilot - Path Management
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
User folder paths and directory initialization.

On first run, o3de-pilot creates:
- ~/.o3de/                    - Config, cache, manifest
- ~/O3DE/                     - Downloaded objects
  ├── Engines/
  ├── Projects/
  ├── Gems/
  ├── Templates/
  ├── Repos/
  └── Overlays/               - New in Schema 2.0.0
"""

from pathlib import Path
from typing import Optional, Union
import os
import json


def to_posix_path(path: Union[Path, str]) -> str:
    """
    Convert a path to POSIX format (forward slashes).
    
    This ensures cross-platform compatibility when writing paths
    to JSON files. Windows paths like C:\\Users\\foo become
    C:/Users/foo.
    
    Args:
        path: A Path object or path string
        
    Returns:
        POSIX-style path string with forward slashes
    """
    if isinstance(path, str):
        path = Path(path)
    return path.as_posix()


def get_home_path() -> Path:
    """Get user's home directory."""
    return Path(os.path.expanduser("~")).resolve()


def get_dot_o3de_path() -> Path:
    """Get ~/.o3de directory path."""
    return get_home_path() / ".o3de"


def get_o3de_path() -> Path:
    """Get ~/O3DE directory path."""
    return get_home_path() / "O3DE"


# ~/.o3de subdirectories
def get_cache_path() -> Path:
    """Get ~/.o3de/Cache directory."""
    return get_dot_o3de_path() / "Cache"


def get_registry_path() -> Path:
    """Get ~/.o3de/Registry directory."""
    return get_dot_o3de_path() / "Registry"


def get_logs_path() -> Path:
    """Get ~/.o3de/Logs directory."""
    return get_dot_o3de_path() / "Logs"


def get_download_path() -> Path:
    """Get ~/.o3de/Download directory (temp downloads)."""
    return get_dot_o3de_path() / "Download"


def get_third_party_path() -> Path:
    """Get ~/.o3de/3rdParty directory."""
    return get_dot_o3de_path() / "3rdParty"


def get_pilot_config_path() -> Path:
    """Get ~/.o3de/pilot/config.yaml path."""
    return get_dot_o3de_path() / "pilot" / "config.yaml"


# Manifest paths
def get_manifest_path() -> Path:
    """
    Get path to o3de_manifest.json.
    
    Prefers the versioned Schema 2.0.0 file (o3de_manifest.2-0-0.json)
    over the legacy file (o3de_manifest.json) if it exists.
    """
    dot_o3de = get_dot_o3de_path()
    
    # Check for versioned 2.0.0 manifest first
    versioned = dot_o3de / "o3de_manifest.2-0-0.json"
    if versioned.exists():
        return versioned
    
    # Fall back to legacy
    return dot_o3de / "o3de_manifest.json"


def get_resolved_manifest_path() -> Path:
    """Get path to resolved_o3de_manifest.json."""
    return get_dot_o3de_path() / "resolved_o3de_manifest.json"


# ~/O3DE subdirectories (default object storage)
def get_default_engines_path() -> Path:
    """Get ~/O3DE/Engines directory."""
    return get_o3de_path() / "Engines"


def get_default_projects_path() -> Path:
    """Get ~/O3DE/Projects directory."""
    return get_o3de_path() / "Projects"


def get_default_gems_path() -> Path:
    """Get ~/O3DE/Gems directory."""
    return get_o3de_path() / "Gems"


def get_default_templates_path() -> Path:
    """Get ~/O3DE/Templates directory."""
    return get_o3de_path() / "Templates"


def get_default_repos_path() -> Path:
    """Get ~/O3DE/Repos directory."""
    return get_o3de_path() / "Repos"


def get_default_overlays_path() -> Path:
    """Get ~/O3DE/Overlays directory."""
    return get_o3de_path() / "Overlays"


# Workspace directory (where symlinked builds are created)
def get_default_workspaces_path() -> Path:
    """Get ~/O3DE/Workspaces directory."""
    return get_o3de_path() / "Workspaces"


# Backward-compatible alias
get_default_layouts_path = get_default_workspaces_path


def get_default_path_for_type(object_type: "ObjectType") -> Path:
    """Get the default install path for an object type."""
    from .models import ObjectType
    
    paths = {
        ObjectType.ENGINE: get_default_engines_path,
        ObjectType.PROJECT: get_default_projects_path,
        ObjectType.GEM: get_default_gems_path,
        ObjectType.TEMPLATE: get_default_templates_path,
        ObjectType.REPO: get_default_repos_path,
        ObjectType.OVERLAY: get_default_overlays_path,
    }
    return paths.get(object_type, get_default_gems_path)()


def ensure_directory(path: Path) -> Path:
    """Create directory if it doesn't exist, return path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def initialize_user_directories() -> dict[str, Path]:
    """
    Initialize all user directories on first run.
    
    Creates:
    - ~/.o3de/ and subdirectories
    - ~/O3DE/ and subdirectories
    
    Returns dict of created paths.
    """
    paths = {
        # ~/.o3de structure
        "dot_o3de": ensure_directory(get_dot_o3de_path()),
        "cache": ensure_directory(get_cache_path()),
        "registry": ensure_directory(get_registry_path()),
        "logs": ensure_directory(get_logs_path()),
        "download": ensure_directory(get_download_path()),
        "third_party": ensure_directory(get_third_party_path()),
        "pilot_config_dir": ensure_directory(get_pilot_config_path().parent),
        
        # ~/O3DE structure
        "o3de": ensure_directory(get_o3de_path()),
        "engines": ensure_directory(get_default_engines_path()),
        "projects": ensure_directory(get_default_projects_path()),
        "gems": ensure_directory(get_default_gems_path()),
        "templates": ensure_directory(get_default_templates_path()),
        "repos": ensure_directory(get_default_repos_path()),
        "overlays": ensure_directory(get_default_overlays_path()),
        "workspaces": ensure_directory(get_default_workspaces_path()),
    }
    
    # Create default manifest if it doesn't exist
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        default_manifest = get_default_manifest_data()
        with open(manifest_path, "w") as f:
            json.dump(default_manifest, f, indent=4)
        paths["manifest"] = manifest_path
    
    return paths


def get_default_manifest_data() -> dict:
    """
    Get default manifest data for new users.
    
    Schema 2.0.0 format.
    """
    user = os.environ.get("USER", os.environ.get("USERNAME", "user"))
    
    return {
        "$schema": "https://canonical.o3de.org/o3de-manifest-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "o3de_manifest": {
            "name": f"me.home.{user}.manifest"
        },
        "default": {
            "engines_path": get_default_engines_path().as_posix(),
            "projects_path": get_default_projects_path().as_posix(),
            "gems_path": get_default_gems_path().as_posix(),
            "templates_path": get_default_templates_path().as_posix(),
            "repos_path": get_default_repos_path().as_posix(),
            "overlays_path": get_default_overlays_path().as_posix(),
            "third_party_path": get_third_party_path().as_posix(),
        },
        "local": {
            "engines": [],
            "projects": [],
            "gems": [],
            "templates": [],
            "repos": [],
            "overlays": [],
        },
        "remote": {
            "engines": [],
            "projects": [],
            "gems": [],
            "templates": [],
            "repos": [
                # Default O3DE community repo
                "https://canonical.o3de.org/repo.json"
            ],
            "overlays": [],
        }
    }


def is_first_run() -> bool:
    """Check if this is first run (no manifest exists)."""
    return not get_manifest_path().exists()


def get_object_json_filename(object_type: str) -> str:
    """
    Get the JSON filename for an object type.
    
    engine -> engine.json
    project -> project.json
    gem -> gem.json
    template -> template.json
    repo -> repo.json
    overlay -> overlay.json
    """
    return f"{object_type}.json"


def get_versioned_object_json_filename(object_type: str, version: str = "2.0.0") -> str:
    """
    Get the versioned JSON filename for an object type.
    
    The versioned file uses dashes instead of dots in the version.
    
    engine, 2.0.0 -> engine.2-0-0.json
    project, 2.0.0 -> project.2-0-0.json
    """
    version_dashed = version.replace(".", "-")
    return f"{object_type}.{version_dashed}.json"


def find_object_json(path: "Path", object_type: str) -> tuple["Path", bool]:
    """
    Find the best object JSON file in a directory.
    
    Prioritizes versioned 2.0.0 file over legacy file.
    
    Args:
        path: Directory to search
        object_type: Object type (engine, project, gem, etc.)
    
    Returns:
        Tuple of (json_path, is_versioned)
        is_versioned indicates if the 2.0.0 version was found
    
    Raises:
        FileNotFoundError if no suitable JSON file exists
    """
    # First check for versioned 2.0.0 file
    versioned_name = get_versioned_object_json_filename(object_type, "2.0.0")
    versioned_path = path / versioned_name
    
    if versioned_path.exists():
        return (versioned_path, True)
    
    # Fall back to legacy file
    legacy_name = get_object_json_filename(object_type)
    legacy_path = path / legacy_name
    
    if legacy_path.exists():
        return (legacy_path, False)
    
    raise FileNotFoundError(f"No {object_type}.json or {versioned_name} in {path}")
