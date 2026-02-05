# O3DE Pilot - Schema Upgrade
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Schema Upgrade Module.

Handles migration between schema versions:
- Version 0 (legacy): No $schema, wild west format
- Version 1.0: More structured but child data embedded in parent
- Version 2.0.0: Formal JSON schema, children by relative path only

The upgrade path is always: 0 → 1.0 → 2.0.0 (incremental)
"""

from pathlib import Path
from typing import Optional, Any, Callable
import json
import logging
import shutil
import re
from datetime import datetime

from .models import ObjectType, get_object_type

logger = logging.getLogger("o3de_pilot.upgrade")


class UpgradeError(Exception):
    """Error during schema upgrade."""
    pass


# Schema version patterns
SCHEMA_URL_PATTERN = re.compile(r"https?://[^/]+/o3de-(\w+)-(\d+\.\d+\.\d+)\.json")


def get_schema_version(data: dict) -> tuple[str, str]:
    """
    Get schema version from object data.
    
    Returns:
        Tuple of (object_type, version_string)
        Version is "0" for legacy, "1.0" or "2.0.0" for versioned
    """
    schema_url = data.get("$schema", "")
    
    if not schema_url:
        # Legacy version 0 - detect type from keys
        if "engine.json" in data or "engine_name" in data:
            return ("engine", "0")
        elif "project.json" in data or "project_name" in data:
            return ("project", "0")
        elif "gem.json" in data or "gem_name" in data:
            return ("gem", "0")
        elif "template.json" in data or "template_name" in data:
            return ("template", "0")
        elif "repo_name" in data or "repos_uri" in data:
            return ("repo", "0")
        elif "o3de_manifest" in data.get("$schema", "") or "engines" in data:
            return ("manifest", "0")
        else:
            return ("unknown", "0")
    
    # Parse schema URL
    match = SCHEMA_URL_PATTERN.match(schema_url)
    if match:
        return (match.group(1), match.group(2))
    
    # Try to extract version from $schemaVersion
    version = data.get("$schemaVersion", "1.0")
    
    # Guess type from URL
    if "engine" in schema_url:
        return ("engine", version)
    elif "project" in schema_url:
        return ("project", version)
    elif "gem" in schema_url:
        return ("gem", version)
    elif "template" in schema_url:
        return ("template", version)
    elif "repo" in schema_url:
        return ("repo", version)
    elif "manifest" in schema_url:
        return ("manifest", version)
    elif "overlay" in schema_url:
        return ("overlay", version)
    
    return ("unknown", version)


def needs_upgrade(data: dict, target_version: str = "2.0.0") -> bool:
    """Check if data needs upgrade to target version."""
    _, current_version = get_schema_version(data)
    
    if current_version == "0":
        return True
    
    from packaging.version import Version
    try:
        return Version(current_version) < Version(target_version)
    except Exception:
        return True


# ============================================================================
# Version 0 → 1.0 Upgrade
# ============================================================================

def upgrade_0_to_1(data: dict, object_type: str) -> dict:
    """
    Upgrade from version 0 (legacy) to version 1.0.
    
    Changes:
    - Add $schema URL
    - Normalize field names (engine_name → origin.name, etc.)
    - Ensure required fields exist
    """
    upgraded = data.copy()
    
    # Add schema
    upgraded["$schema"] = f"https://o3de.org/o3de-{object_type}-1.0.json"
    upgraded["$schemaVersion"] = "1.0"
    
    if object_type == "engine":
        upgraded = _upgrade_engine_0_to_1(upgraded)
    elif object_type == "project":
        upgraded = _upgrade_project_0_to_1(upgraded)
    elif object_type == "gem":
        upgraded = _upgrade_gem_0_to_1(upgraded)
    elif object_type == "template":
        upgraded = _upgrade_template_0_to_1(upgraded)
    elif object_type == "repo":
        upgraded = _upgrade_repo_0_to_1(upgraded)
    elif object_type == "manifest":
        upgraded = _upgrade_manifest_0_to_1(upgraded)
    
    return upgraded


def _upgrade_engine_0_to_1(data: dict) -> dict:
    """Upgrade engine from v0 to v1."""
    # Normalize name field
    if "engine_name" in data and "origin" not in data:
        data["origin"] = {"name": data.pop("engine_name")}
    
    # Add version if missing
    if "version" not in data.get("origin", {}):
        if "version" in data:
            data.setdefault("origin", {})["version"] = data.pop("version")
        else:
            data.setdefault("origin", {})["version"] = "0.0.0"
    
    # Ensure origin.type
    data.setdefault("origin", {}).setdefault("type", "engine")
    
    # Convert external_subdirectories to children with explicit JSON paths
    # Note: external_subdirectories shouldn't contain O3DE objects, but often do
    # due to historical confusion. We assume gems since that's most common.
    if "external_subdirectories" in data:
        children = data.setdefault("children", {})
        gems = children.setdefault("gems", [])
        for subdir in data.pop("external_subdirectories"):
            explicit_path = _ensure_explicit_json_path(subdir, "gems")
            if explicit_path not in gems:
                gems.append(explicit_path)
    
    # Convert restricted_name to overlay references  
    if "restricted_name" in data:
        restricted = data.pop("restricted_name")
        data.setdefault("overlays", []).append(restricted)
    
    return data


def _upgrade_project_0_to_1(data: dict) -> dict:
    """Upgrade project from v0 to v1."""
    if "project_name" in data and "origin" not in data:
        data["origin"] = {"name": data.pop("project_name")}
    
    if "version" not in data.get("origin", {}):
        if "version" in data:
            data.setdefault("origin", {})["version"] = data.pop("version")
        else:
            data.setdefault("origin", {})["version"] = "0.0.0"
    
    data.setdefault("origin", {}).setdefault("type", "project")
    
    # Handle engine_path
    if "engine_path" in data:
        data["engine"] = data.pop("engine_path")
    
    # Convert external_subdirectories to children with explicit JSON paths
    # Note: external_subdirectories shouldn't contain O3DE objects, but often do
    # due to historical confusion. We assume gems since that's most common.
    if "external_subdirectories" in data:
        children = data.setdefault("children", {})
        gems = children.setdefault("gems", [])
        for subdir in data.pop("external_subdirectories"):
            explicit_path = _ensure_explicit_json_path(subdir, "gems")
            if explicit_path not in gems:
                gems.append(explicit_path)
    
    if "restricted_name" in data:
        restricted = data.pop("restricted_name")
        data.setdefault("overlays", []).append(restricted)
    
    return data


def _upgrade_gem_0_to_1(data: dict) -> dict:
    """Upgrade gem from v0 to v1."""
    if "gem_name" in data and "origin" not in data:
        data["origin"] = {"name": data.pop("gem_name")}
    
    if "version" not in data.get("origin", {}):
        if "version" in data:
            data.setdefault("origin", {})["version"] = data.pop("version")
        else:
            data.setdefault("origin", {})["version"] = "0.0.0"
    
    data.setdefault("origin", {}).setdefault("type", "gem")
    
    # Convert external_subdirectories to children with explicit JSON paths
    # Gems often have sub-gems in external_subdirectories
    if "external_subdirectories" in data:
        children = data.setdefault("children", {})
        gems = children.setdefault("gems", [])
        for subdir in data.pop("external_subdirectories"):
            explicit_path = _ensure_explicit_json_path(subdir, "gems")
            if explicit_path not in gems:
                gems.append(explicit_path)
    
    # Convert dependencies list to new format
    if "dependencies" in data:
        deps = data["dependencies"]
        if isinstance(deps, list):
            # Old: ["gem1", "gem2"]
            data["dependencies"] = {"gems": deps}
    
    if "restricted_name" in data:
        restricted = data.pop("restricted_name")
        data.setdefault("overlays", []).append(restricted)
    
    return data


def _upgrade_template_0_to_1(data: dict) -> dict:
    """Upgrade template from v0 to v1."""
    if "template_name" in data and "origin" not in data:
        data["origin"] = {"name": data.pop("template_name")}
    
    if "version" not in data.get("origin", {}):
        if "version" in data:
            data.setdefault("origin", {})["version"] = data.pop("version")
        else:
            data.setdefault("origin", {})["version"] = "0.0.0"
    
    data.setdefault("origin", {}).setdefault("type", "template")
    
    return data


def _upgrade_repo_0_to_1(data: dict) -> dict:
    """Upgrade repo from v0 to v1."""
    if "repo_name" in data and "origin" not in data:
        data["origin"] = {"name": data.pop("repo_name")}
    
    if "repo_uri" in data:
        data["uri"] = data.pop("repo_uri")
    
    data.setdefault("origin", {}).setdefault("type", "repo")
    data.setdefault("origin", {}).setdefault("version", "0.0.0")
    
    return data


def _upgrade_manifest_0_to_1(data: dict) -> dict:
    """Upgrade manifest from v0 to v1."""
    data["$schema"] = "https://o3de.org/o3de-manifest-1.0.json"
    
    # Wrap lists in 'local' object if needed
    if "local" not in data:
        local = {}
        for key in ["engines", "projects", "gems", "templates", "repos"]:
            if key in data and isinstance(data[key], list):
                paths = []
                for item in data.pop(key):
                    if isinstance(item, str):
                        paths.append(item)
                    elif isinstance(item, dict) and "path" in item:
                        paths.append(item["path"])
                if paths:
                    local[key] = paths
        
        if local:
            data["local"] = local
    
    return data


# ============================================================================
# Version 1.0 → 2.0.0 Upgrade
# ============================================================================

SCHEMA_HOSTS = {
    "2.0.0": "https://overlo3de.com",  # Current development host
    # "2.0.0": "https://canonical.o3de.org",  # Future production host
}


def upgrade_1_to_2(data: dict, object_type: str) -> dict:
    """
    Upgrade from version 1.0 to version 2.0.0.
    
    Changes:
    - Update $schema URL to 2.0.0
    - Remove embedded child data (children become relative paths only)
    - Add $schemaVersion field
    - Normalize overlay references
    """
    upgraded = data.copy()
    
    # Update schema
    host = SCHEMA_HOSTS.get("2.0.0", "https://overlo3de.com")
    upgraded["$schema"] = f"{host}/o3de-{object_type}-2.0.0.json"
    upgraded["$schemaVersion"] = "2.0.0"
    
    if object_type == "engine":
        upgraded = _upgrade_engine_1_to_2(upgraded)
    elif object_type == "project":
        upgraded = _upgrade_project_1_to_2(upgraded) 
    elif object_type == "gem":
        upgraded = _upgrade_gem_1_to_2(upgraded)
    elif object_type == "template":
        upgraded = _upgrade_template_1_to_2(upgraded)
    elif object_type == "repo":
        upgraded = _upgrade_repo_1_to_2(upgraded)
    elif object_type == "manifest":
        upgraded = _upgrade_manifest_1_to_2(upgraded)
    
    return upgraded


def _get_json_filename_for_type(type_key: str) -> str:
    """
    Get the JSON filename for a given children type key.
    
    gems -> gem.json, projects -> project.json, etc.
    """
    singular = type_key.rstrip("s")
    return f"{singular}.json"


def _ensure_explicit_json_path(path: str, type_key: str) -> str:
    """
    Ensure a children path includes the explicit JSON filename.
    
    Schema 2.0.0 requires explicit paths like "Gems/MyGem/gem.json"
    not just "Gems/MyGem".
    """
    if path.endswith(".json"):
        return path  # Already explicit
    
    json_filename = _get_json_filename_for_type(type_key)
    # Normalize path separators and append JSON filename
    path = path.rstrip("/\\") 
    return f"{path}/{json_filename}"


def _strip_embedded_data(children: Any) -> dict[str, list[str]]:
    """
    Convert children with embedded data to explicit JSON paths.
    
    Input could be:
    - {"gems": ["Gems/MyGem"]}  # Legacy format
    - {"gems": [{"path": "Gems/MyGem", "gem_name": "..."}]}  # Embedded data
    
    Output: {"gems": ["Gems/MyGem/gem.json"]}  # Explicit paths
    """
    if not isinstance(children, dict):
        return {}
    
    result = {}
    for key, items in children.items():
        if not isinstance(items, list):
            continue
        
        paths = []
        for item in items:
            if isinstance(item, str):
                paths.append(_ensure_explicit_json_path(item, key))
            elif isinstance(item, dict):
                # Extract path from embedded data
                path = item.get("path", item.get("gem_path", item.get("project_path", "")))
                if path:
                    paths.append(_ensure_explicit_json_path(path, key))
        
        if paths:
            result[key] = paths
    
    return result


def _upgrade_engine_1_to_2(data: dict) -> dict:
    """Upgrade engine from v1 to v2."""
    # Strip embedded child data
    if "children" in data:
        data["children"] = _strip_embedded_data(data["children"])
    
    # Convert overlays list to proper format
    if "overlays" in data:
        data["overlays"] = [
            o if isinstance(o, str) else o.get("name", str(o))
            for o in data["overlays"]
        ]
    
    return data


def _upgrade_project_1_to_2(data: dict) -> dict:
    """Upgrade project from v1 to v2."""
    if "children" in data:
        data["children"] = _strip_embedded_data(data["children"])
    
    if "overlays" in data:
        data["overlays"] = [
            o if isinstance(o, str) else o.get("name", str(o))
            for o in data["overlays"]
        ]
    
    return data


def _upgrade_gem_1_to_2(data: dict) -> dict:
    """Upgrade gem from v1 to v2."""
    if "children" in data:
        data["children"] = _strip_embedded_data(data["children"])
    
    return data


def _upgrade_template_1_to_2(data: dict) -> dict:
    """Upgrade template from v1 to v2."""
    if "children" in data:
        data["children"] = _strip_embedded_data(data["children"])
    
    return data


def _upgrade_repo_1_to_2(data: dict) -> dict:
    """Upgrade repo from v1 to v2."""
    # Repos mostly stay the same
    return data


def _upgrade_manifest_1_to_2(data: dict) -> dict:
    """Upgrade manifest from v1 to v2."""
    # Add overlays list if not present
    local = data.get("local", {})
    if "overlays" not in local:
        local["overlays"] = []
        data["local"] = local
    
    return data


# ============================================================================
# Full Upgrade Path
# ============================================================================

def upgrade_to_latest(
    data: dict,
    object_type: Optional[str] = None,
) -> dict:
    """
    Upgrade data to latest schema version (2.0.0).
    
    Args:
        data: Object data dict
        object_type: Optional type hint (auto-detected if not provided)
    
    Returns:
        Upgraded data dict
    """
    current_type, current_version = get_schema_version(data)
    
    if object_type:
        current_type = object_type
    
    if current_type == "unknown":
        raise UpgradeError("Cannot detect object type for upgrade")
    
    upgraded = data
    
    # Upgrade 0 → 1.0
    if current_version == "0":
        upgraded = upgrade_0_to_1(upgraded, current_type)
        current_version = "1.0"
    
    # Upgrade 1.0 → 2.0.0
    if current_version == "1.0":
        upgraded = upgrade_1_to_2(upgraded, current_type)
        current_version = "2.0.0"
    
    return upgraded


def upgrade_file(
    path: Path,
    backup: bool = True,
) -> tuple[Path, str, str]:
    """
    Upgrade a single JSON file to latest schema.
    
    Args:
        path: Path to JSON file
        backup: Create .bak backup before modifying
    
    Returns:
        Tuple of (path, old_version, new_version)
    """
    with open(path, "r") as f:
        data = json.load(f)
    
    old_type, old_version = get_schema_version(data)
    
    if not needs_upgrade(data):
        return (path, old_version, old_version)
    
    # Backup
    if backup:
        backup_path = path.with_suffix(f".{old_version}.bak.json")
        shutil.copy(path, backup_path)
        logger.info(f"Backed up: {backup_path}")
    
    # Upgrade
    upgraded = upgrade_to_latest(data, old_type)
    new_type, new_version = get_schema_version(upgraded)
    
    # Write
    with open(path, "w") as f:
        json.dump(upgraded, f, indent=2)
    
    logger.info(f"Upgraded {path}: {old_version} → {new_version}")
    return (path, old_version, new_version)


def upgrade_directory(
    root: Path,
    recursive: bool = True,
    backup: bool = True,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> list[tuple[Path, str, str]]:
    """
    Upgrade all O3DE JSON files in a directory.
    
    Args:
        root: Root directory to scan
        recursive: Search recursively
        backup: Create backups
        progress_callback: Progress callback
    
    Returns:
        List of (path, old_version, new_version) for upgraded files
    """
    json_files = ["engine.json", "project.json", "gem.json", "template.json", "repo.json", "overlay.json"]
    
    paths = []
    if recursive:
        for pattern in json_files:
            paths.extend(root.rglob(pattern))
    else:
        for pattern in json_files:
            candidate = root / pattern
            if candidate.exists():
                paths.append(candidate)
    
    results = []
    total = len(paths)
    
    for i, path in enumerate(paths, 1):
        if progress_callback:
            progress_callback(f"Upgrading {path.name}", i, total)
        
        try:
            result = upgrade_file(path, backup=backup)
            if result[1] != result[2]:  # Only include if actually upgraded
                results.append(result)
        except Exception as e:
            logger.warning(f"Failed to upgrade {path}: {e}")
    
    return results
