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
    "restricted": "restricted.json",  # Legacy, maps to overlay
}


def detect_object_type(path: Path) -> str | None:
    """Detect object type from directory contents."""
    for obj_type, json_file in OBJECT_JSON_FILES.items():
        if (path / json_file).exists():
            return obj_type
    return None


def check_and_upgrade_object(obj_path: Path, obj_type: str, force: bool = False) -> bool:
    """
    Check if an object needs schema upgrade and upgrade if necessary.
    
    The upgrade is non-destructive - original files are preserved with .bak extension.
    
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
    obj_path: Path,
    obj_type: str,
    remove: bool = False,
) -> bool:
    """
    Register or unregister an object path in the manifest.
    
    Args:
        manifest_data: The manifest JSON data (modified in place)
        obj_path: Path to the object
        obj_type: Object type
        remove: If True, remove instead of add
        
    Returns:
        True if successful
    """
    # Map type to manifest key
    key = f"{obj_type}s"
    local = manifest_data.setdefault("local", {})
    type_list = local.setdefault(key, [])
    
    path_str = str(obj_path)
    
    # Normalize paths for comparison
    normalized = [Path(p).resolve() for p in type_list if p]
    obj_resolved = obj_path.resolve()
    
    if remove:
        # Remove path
        new_list = [p for p in type_list if Path(p).resolve() != obj_resolved]
        local[key] = new_list
        return len(new_list) < len(type_list)  # True if removed
    else:
        # Add path if not already present
        if obj_resolved not in normalized:
            type_list.insert(0, path_str)
            return True
        return False  # Already registered


@click.group()
def register() -> None:
    """Register O3DE objects in the manifest.
    
    Registration adds object paths to o3de_manifest.2-0-0.json.
    Objects that need schema upgrades are upgraded non-destructively.
    """
    pass


@register.command("add")
@click.argument("path", type=click.Path(exists=True))
@click.option("--type", "-t", "obj_type",
              type=click.Choice(["engine", "project", "gem", "template", "repo", "overlay"]),
              help="Object type (auto-detected if not specified)")
@click.option("--force", "-f", is_flag=True, help="Force re-upgrade even if at target version")
@click.option("--no-upgrade", is_flag=True, help="Skip schema upgrade check")
def register_add(path: str, obj_type: str | None, force: bool, no_upgrade: bool) -> None:
    """Register an object in the manifest.
    
    Adds the object at PATH to the local manifest. Auto-detects type
    if not specified. Upgrades object schema to 2.0.0 if needed.
    """
    obj_path = Path(path).resolve()
    
    # Auto-detect type
    if not obj_type:
        obj_type = detect_object_type(obj_path)
        if not obj_type:
            console.print("[red]Could not detect object type.[/red]")
            console.print("Use --type to specify: engine, project, gem, template, repo, overlay")
            raise SystemExit(1)
        console.print(f"[dim]Detected type: {obj_type}[/dim]")
    
    # Check and upgrade object schema if needed
    if not no_upgrade:
        if not check_and_upgrade_object(obj_path, obj_type, force):
            console.print("[red]Registration aborted due to upgrade failure.[/red]")
            console.print("Use --no-upgrade to skip schema upgrade.")
            raise SystemExit(1)
    
    # Ensure 2.0.0 manifest exists
    manifest_path = ensure_manifest_2()
    
    # Load manifest
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    # Register the object
    if register_object_path(manifest_data, obj_path, obj_type, remove=False):
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        console.print(f"[green]Registered {obj_type}:[/green] {obj_path.name}")
    else:
        console.print(f"[yellow]Already registered:[/yellow] {obj_path.name}")


@register.command("remove")
@click.argument("path", type=click.Path())
@click.option("--type", "-t", "obj_type",
              type=click.Choice(["engine", "project", "gem", "template", "repo", "overlay"]),
              help="Object type (auto-detected if not specified)")
def register_remove(path: str, obj_type: str | None) -> None:
    """Unregister an object from the manifest.
    
    Removes the object at PATH from the local manifest.
    Does not delete any files.
    """
    obj_path = Path(path).resolve()
    
    # Auto-detect type if path exists
    if not obj_type and obj_path.exists():
        obj_type = detect_object_type(obj_path)
    
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    removed = False
    if obj_type:
        removed = register_object_path(manifest_data, obj_path, obj_type, remove=True)
    else:
        # Try all types
        local = manifest_data.get("local", {})
        for type_key in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
            type_list = local.get(type_key, [])
            new_list = [p for p in type_list if Path(p).resolve() != obj_path]
            if len(new_list) < len(type_list):
                local[type_key] = new_list
                removed = True
                break
    
    if removed:
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest_data, f, indent=2)
        console.print(f"[green]Unregistered:[/green] {obj_path.name}")
    else:
        console.print(f"[yellow]Not found in manifest:[/yellow] {path}")


@register.command("all")
@click.argument("path", type=click.Path(exists=True))
@click.option("--type", "-t", "obj_type",
              type=click.Choice(["engine", "project", "gem", "template", "repo", "overlay", "all"]),
              default="all",
              help="Object type to register (default: all)")
@click.option("--force", "-f", is_flag=True, help="Force re-upgrade even if at target version")
@click.option("--no-upgrade", is_flag=True, help="Skip schema upgrade check")
def register_all(path: str, obj_type: str, force: bool, no_upgrade: bool) -> None:
    """Register all objects in a directory.
    
    Recursively scans PATH for O3DE objects and registers them.
    """
    import os
    
    root_path = Path(path).resolve()
    
    types_to_find = (
        list(OBJECT_JSON_FILES.keys()) if obj_type == "all" 
        else [obj_type]
    )
    
    found = []
    for curr_root, dirs, files in os.walk(root_path):
        for type_name in types_to_find:
            json_file = OBJECT_JSON_FILES.get(type_name)
            if json_file and json_file in files:
                found.append((Path(curr_root), type_name))
                # Don't recurse into object directories
                dirs[:] = []
                break
    
    if not found:
        console.print(f"[yellow]No objects found in:[/yellow] {root_path}")
        return
    
    console.print(f"[bold]Found {len(found)} objects to register[/bold]")
    
    # Ensure manifest exists
    manifest_path = ensure_manifest_2()
    
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)
    
    registered = 0
    for obj_path, type_name in found:
        # Upgrade if needed
        if not no_upgrade:
            if not check_and_upgrade_object(obj_path, type_name, force):
                console.print(f"[red]Skipping (upgrade failed):[/red] {obj_path.name}")
                continue
        
        if register_object_path(manifest_data, obj_path, type_name, remove=False):
            console.print(f"[green]Registered {type_name}:[/green] {obj_path.name}")
            registered += 1
        else:
            console.print(f"[dim]Already registered:[/dim] {obj_path.name}")
    
    # Save manifest
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    
    console.print(f"\n[bold green]Registered {registered} objects[/bold green]")


@register.command("status")
@click.argument("path", type=click.Path(exists=True))
def register_status(path: str) -> None:
    """Check registration and schema status of an object.
    
    Shows whether the object at PATH is registered and its schema version.
    """
    obj_path = Path(path).resolve()
    
    # Detect type
    obj_type = detect_object_type(obj_path)
    if not obj_type:
        console.print(f"[red]No O3DE object found at:[/red] {obj_path}")
        raise SystemExit(1)
    
    json_file = OBJECT_JSON_FILES[obj_type]
    json_path = obj_path / json_file
    
    # Load and check schema
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    detected_type, version = get_schema_version(data)
    upgrade_needed = needs_upgrade(data, "2.0.0")
    
    console.print(f"[bold]Object:[/bold] {obj_path.name}")
    console.print(f"  Type: {obj_type}")
    console.print(f"  Schema: {version}")
    
    if upgrade_needed:
        console.print(f"  [yellow]Upgrade needed to 2.0.0[/yellow]")
    else:
        console.print(f"  [green]Schema is current[/green]")
    
    # Check registration
    manifest_path = get_manifest_path()
    if manifest_path.exists():
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)
        
        local = manifest_data.get("local", {})
        type_list = local.get(f"{obj_type}s", [])
        
        registered = any(Path(p).resolve() == obj_path for p in type_list)
        
        if registered:
            console.print(f"  [green]Registered in manifest[/green]")
        else:
            console.print(f"  [yellow]Not registered[/yellow]")
    else:
        console.print(f"  [yellow]No manifest found[/yellow]")
