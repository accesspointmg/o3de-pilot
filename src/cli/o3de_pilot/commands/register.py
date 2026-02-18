# O3DE Pilot CLI - Register Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Object registration commands.

Registers O3DE objects (engines, projects, gems, templates, repos, overlays) 
in the o3de_manifest.json. Handles schema upgrades transparently.
"""

import click
import json
from pathlib import Path
from rich.console import Console

from o3de_pilot.core import (
    get_manifest_path,
    ObjectType,
)
from o3de_pilot.core.upgrade import (
    needs_upgrade,
    get_schema_version,
    upgrade_file,
)

console = Console()


# Object type to JSON file name mapping
OBJECT_JSON_FILES = {
    "engine": "engine.json",
    "project": "project.json",
    "gem": "gem.json",
    "template": "template.json",
    "repo": "repo.json",
    "overlay": "overlay.json",
    "restricted": "restricted.json",  # Legacy type with no upgrade path
}


def detect_object_type(path: Path) -> str | None:
    """Detect object type from directory contents."""
    for obj_type, json_file in OBJECT_JSON_FILES.items():
        if (path / json_file).exists():
            return obj_type
    return None


def resolve_to_json(path: Path, obj_type: str | None = None) -> tuple[Path, str] | None:
    """Resolve *path* to an explicit JSON file path and its type.

    *path* may be:
    - A JSON file (e.g. ``gem.json``) — returned as-is with inferred type.
    - A directory containing an O3DE JSON file — resolved to that file.

    Returns ``(json_path, obj_type)`` or ``None`` if nothing was found.
    """
    path = path.resolve()

    if path.is_file() and path.suffix == ".json":
        # Already a JSON file — infer type from filename
        if not obj_type:
            for otype, jfile in OBJECT_JSON_FILES.items():
                if path.name == jfile:
                    obj_type = otype
                    break
        return (path, obj_type) if obj_type else None

    if path.is_dir():
        # If a specific type was requested, look for that file only
        if obj_type:
            candidate = path / OBJECT_JSON_FILES[obj_type]
            if candidate.exists():
                return (candidate, obj_type)
            return None
        # Auto-detect: try each known JSON filename
        for otype, jfile in OBJECT_JSON_FILES.items():
            candidate = path / jfile
            if candidate.exists():
                return (candidate, otype)
    return None


def _get_all_registered_paths(manifest_data: dict) -> list[Path]:
    """Return all resolved local *directory* paths registered in the manifest.

    Manifest entries are JSON file paths; this normalises them to their
    parent directory so that guard checks (child-of, already-registered)
    work on directory identity.
    """
    local = manifest_data.get("local", {})
    paths = []
    for key in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
        for p in local.get(key, []):
            if p:
                resolved = Path(p).resolve()
                if resolved.suffix == ".json":
                    resolved = resolved.parent
                paths.append(resolved)
    return paths


def is_child_of_registered(obj_path: Path, manifest_data: dict) -> Path | None:
    """Check if *obj_path* is a descendant of an already-registered object.

    Returns the registered ancestor path if found, else None.
    """
    obj_resolved = obj_path.resolve()
    for reg_path in _get_all_registered_paths(manifest_data):
        if reg_path == obj_resolved:
            continue  # Same path – not a *child*
        try:
            obj_resolved.relative_to(reg_path)
            return reg_path  # obj_path is inside reg_path
        except ValueError:
            continue
    return None


def is_directly_registered(obj_path: Path, manifest_data: dict) -> bool:
    """Check if *obj_path* is directly listed in the manifest (not a child)."""
    obj_resolved = obj_path.resolve()
    for reg_path in _get_all_registered_paths(manifest_data):
        if reg_path == obj_resolved:
            return True
    return False


def check_and_upgrade_object(obj_path: Path, obj_type: str, force: bool = False) -> bool:
    """
    Check if an object needs schema upgrade and upgrade if necessary.
    
    The upgrade is non-destructive — creates a sidecar file (e.g. gem.2-0-0.json)
    and leaves the original untouched.
    
    Args:
        obj_path: Path to the object directory
        obj_type: Object type (engine, project, gem, etc.)
        force: Force upgrade even if already at target version
        
    Returns:
        True if object is at schema 2.0.0 (or was upgraded), False on error
    """
    json_file = OBJECT_JSON_FILES.get(obj_type)
    if not json_file:
        console.print(f"[red]Unknown object type:[/red] {obj_type}")
        return False
    
    # Check for existing sidecar first
    from o3de_pilot.core.paths import get_versioned_object_json_filename
    versioned_name = get_versioned_object_json_filename(obj_type, "2.0.0")
    versioned_path = obj_path / versioned_name
    if versioned_path.exists() and not force:
        return True
    
    json_path = obj_path / json_file
    if not json_path.exists():
        console.print(f"[red]Object JSON not found:[/red] {json_path}")
        return False
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        console.print(f"[red]Invalid JSON in {json_path}:[/red] {e}")
        return False
    
    # Check schema version
    detected_type, version = get_schema_version(data)
    
    if version == "2.0.0" and not force:
        # Already at target version
        return True
    
    if needs_upgrade(data, "2.0.0"):
        console.print(f"[yellow]Object needs upgrade to schema 2.0.0:[/yellow] {obj_path.name}")
        console.print(f"  Current version: {version}")
        
        try:
            # Perform upgrade (non-destructive - creates backup)
            result = upgrade_file(json_path, backup=True)
            if result:
                _, old_ver, new_ver = result
                console.print(f"[green]Upgraded:[/green] {json_path.name} ({old_ver} → {new_ver})")
                return True
            else:
                console.print(f"[red]Upgrade failed for:[/red] {json_path}")
                return False
        except Exception as e:
            console.print(f"[red]Upgrade error:[/red] {e}")
            return False
    
    return True


def get_manifest_2_path() -> Path:
    """Get path to the 2.0.0 manifest file."""
    from o3de_pilot.core.paths import get_dot_o3de_path
    return get_dot_o3de_path() / "o3de_manifest.2-0-0.json"


def _ensure_default_dirs(manifest_path: Path) -> None:
    """Create default directories listed in the manifest if they don't exist."""
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return
    defaults = data.get("default", {})
    for key in ("repos_path", "overlays_path"):
        dir_str = defaults.get(key, "")
        if dir_str:
            Path(dir_str).mkdir(parents=True, exist_ok=True)


def ensure_manifest_2() -> Path:
    """
    Ensure o3de_manifest.2-0-0.json exists.
    
    If only legacy manifest exists, upgrade it non-destructively.
    If neither exists, create a new 2.0.0 manifest.
    
    Returns:
        Path to the 2.0.0 manifest
    """
    from o3de_pilot.core.paths import get_dot_o3de_path
    
    dot_o3de = get_dot_o3de_path()
    versioned = dot_o3de / "o3de_manifest.2-0-0.json"
    legacy = dot_o3de / "o3de_manifest.json"
    
    if versioned.exists():
        return versioned
    
    if legacy.exists():
        # Upgrade legacy manifest
        console.print("[yellow]Upgrading manifest to schema 2.0.0...[/yellow]")
        
        try:
            with open(legacy, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            # Create fresh manifest if legacy is corrupt
            data = {}
        
        if needs_upgrade(data, "2.0.0"):
            result = upgrade_file(legacy, target_version="2.0.0", backup=True)
            if result:
                console.print(f"[green]Manifest upgraded to 2.0.0[/green]")
                # The upgrade_file should create the versioned file
                if versioned.exists():
                    _ensure_default_dirs(versioned)
                    return versioned
    
    # Create new 2.0.0 manifest
    from o3de_pilot.core.paths import get_default_manifest_data
    manifest_data = get_default_manifest_data()
    
    dot_o3de.mkdir(parents=True, exist_ok=True)
    with open(versioned, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    
    console.print(f"[green]Created manifest:[/green] {versioned}")
    return versioned


def register_object_path(
    manifest_data: dict,
    json_path: Path,
    obj_type: str,
    remove: bool = False,
) -> bool:
    """Register or unregister an object JSON file path in the manifest.

    All manifest entries are stored as POSIX paths to JSON files
    (e.g. ``C:/Users/me/MyGem/gem.json``).  Comparison is by resolved
    parent directory so that ``gem.json`` and ``gem.2-0-0.json`` map
    to the same object.

    Args:
        manifest_data: Manifest JSON data (modified in place).
        json_path: Absolute path to the object's JSON file.
        obj_type: Object type string (engine, gem, …).
        remove: If True, remove instead of add.

    Returns:
        True if the manifest was changed.
    """
    key = f"{obj_type}s"
    local = manifest_data.setdefault("local", {})
    type_list = local.setdefault(key, [])

    path_str = json_path.as_posix()
    obj_dir = json_path.resolve()
    if obj_dir.suffix == ".json":
        obj_dir = obj_dir.parent

    def _dir(p: str) -> Path:
        r = Path(p).resolve()
        return r.parent if r.suffix == ".json" else r

    if remove:
        new_list = [p for p in type_list if _dir(p) != obj_dir]
        local[key] = new_list
        return len(new_list) < len(type_list)
    else:
        if any(_dir(p) == obj_dir for p in type_list):
            return False  # Already registered
        type_list.insert(0, path_str)
        return True


@click.command()
@click.argument("path_or_url")
@click.option("--type", "-t", "obj_type",
              type=click.Choice(["engine", "project", "gem", "template", "repo", "overlay"]),
              help="Object type (auto-detected if not specified)")
@click.option("--remote", is_flag=True, help="Register a remote URL instead of a local path")
@click.option("--force", "-f", is_flag=True, help="Force re-upgrade even if at target version")
@click.option("--no-upgrade", is_flag=True, help="Skip schema upgrade check")
def register(path_or_url: str, obj_type: str | None, remote: bool, force: bool, no_upgrade: bool) -> None:
    """Register an O3DE object in the manifest.

    PATH_OR_URL is the path to an O3DE JSON file (e.g. gem.json,
    engine.json) or a directory containing one.  The manifest always
    stores the full JSON file path.

    Use --remote to register a remote URL.
    """
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        # Try to create the 2.0.0 manifest
        manifest_path = ensure_manifest_2()
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    if remote:
        # Remote registration — add URL to remote section
        if not obj_type:
            # Try to infer type from URL filename
            url_lower = path_or_url.lower()
            for otype, jfile in OBJECT_JSON_FILES.items():
                if url_lower.endswith(jfile) or f"/{otype}" in url_lower:
                    obj_type = otype
                    break
            if not obj_type:
                obj_type = "gem"  # Default to gem for remote
                console.print(f"[dim]Defaulting to type: {obj_type}[/dim]")
        
        section = manifest_data.setdefault("remote", {})
        type_list = section.setdefault(f"{obj_type}s", [])
        if path_or_url in type_list:
            console.print(f"[yellow]Already registered:[/yellow] {path_or_url}")
            return
        type_list.append(path_or_url)
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        console.print(f"[green]Registered remote {obj_type}:[/green] {path_or_url}")
        return
    
    # Local registration — resolve to a concrete JSON file path
    raw_path = Path(path_or_url).resolve()

    if not raw_path.exists():
        console.print(f"[red]Path does not exist:[/red] {path_or_url}")
        raise SystemExit(1)

    result = resolve_to_json(raw_path, obj_type)
    if result is None:
        console.print("[red]Could not find an O3DE JSON file.[/red]")
        console.print("Please select an engine.json, gem.json, project.json, template.json, repo.json, or overlay.json.")
        raise SystemExit(1)

    json_file_path, obj_type = result
    obj_dir = json_file_path.parent  # directory used for guards / upgrade
    console.print(f"[dim]Detected type: {obj_type}[/dim]")

    # Guard: already registered?
    if is_directly_registered(obj_dir, manifest_data):
        console.print(f"[yellow]Already registered:[/yellow] {obj_dir.name}")
        return

    # Guard: child of an already-registered object?
    ancestor = is_child_of_registered(obj_dir, manifest_data)
    if ancestor:
        console.print(
            f"[yellow]Already covered:[/yellow] {obj_dir.name} is a child of "
            f"registered object at {ancestor}"
        )
        return

    # Check and upgrade object schema if needed
    if not no_upgrade:
        if not check_and_upgrade_object(obj_dir, obj_type, force):
            console.print("[red]Registration aborted due to upgrade failure.[/red]")
            console.print("Use --no-upgrade to skip schema upgrade.")
            raise SystemExit(1)

    # Ensure 2.0.0 manifest exists
    manifest_path = ensure_manifest_2()

    # Load manifest
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    # Register the full JSON file path
    if register_object_path(manifest_data, json_file_path, obj_type, remove=False):
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        console.print(f"[green]Registered {obj_type}:[/green] {json_file_path.as_posix()}")
    else:
        console.print(f"[yellow]Already registered:[/yellow] {obj_dir.name}")


@click.command()
@click.argument("path_or_name")
@click.option("--type", "-t", "obj_type",
              type=click.Choice(["engine", "project", "gem", "template", "repo", "overlay"]),
              help="Object type (auto-detected if not specified)")
@click.option("--remote", is_flag=True, help="Remove from remote section instead of local")
def unregister(path_or_name: str, obj_type: str | None, remote: bool) -> None:
    """Unregister an O3DE object from the manifest.
    
    Removes the object at PATH_OR_NAME from the manifest.
    Does not delete any files. Use --remote to remove a remote URL.
    """
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    if remote:
        # Remove from remote section
        section = manifest_data.get("remote", {})
        removed = False
        for type_key in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
            type_list = section.get(type_key, [])
            if path_or_name in type_list:
                type_list.remove(path_or_name)
                removed = True
                break
        if removed:
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest_data, f, indent=2)
            console.print(f"[green]Unregistered remote:[/green] {path_or_name}")
        else:
            console.print(f"[yellow]Not found in remote manifest:[/yellow] {path_or_name}")
        return
    
    raw_path = Path(path_or_name).resolve()

    # Resolve to directory for guard checks (handles both JSON file and dir args)
    obj_dir = raw_path.parent if raw_path.suffix == ".json" else raw_path

    # Auto-detect type if possible
    if not obj_type and obj_dir.exists():
        obj_type = detect_object_type(obj_dir)

    # Guard: child of a registered object cannot be unregistered independently
    ancestor = is_child_of_registered(obj_dir, manifest_data)
    if ancestor and not is_directly_registered(obj_dir, manifest_data):
        console.print(
            f"[yellow]Cannot unregister:[/yellow] {obj_dir.name} is a child of "
            f"registered object at {ancestor}"
        )
        return

    # Guard: not registered at all
    if not is_directly_registered(obj_dir, manifest_data):
        console.print(f"[yellow]Not registered:[/yellow] {path_or_name}")
        return

    # Remove — match by resolved parent directory so it works regardless
    # of whether the user passed a JSON file or a directory.
    removed = False
    local = manifest_data.get("local", {})
    for type_key in ([f"{obj_type}s"] if obj_type else
                     ["engines", "projects", "gems", "templates", "repos", "overlays"]):
        type_list = local.get(type_key, [])
        new_list = []
        for p in type_list:
            entry_dir = Path(p).resolve()
            if entry_dir.suffix == ".json":
                entry_dir = entry_dir.parent
            if entry_dir == obj_dir:
                removed = True  # skip this entry
            else:
                new_list.append(p)
        if removed:
            local[type_key] = new_list
            break

    if removed:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        console.print(f"[green]Unregistered:[/green] {obj_dir.name}")
    else:
        console.print(f"[yellow]Not found in manifest:[/yellow] {path_or_name}")


