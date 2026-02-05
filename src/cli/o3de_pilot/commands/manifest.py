# O3DE Pilot CLI - Manifest Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Manifest resolution and management commands."""

import click
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from o3de_pilot.core import (
    get_manifest_path,
    get_resolved_manifest_path,
    resolve_manifest,
    Resolver,
    ObjectType,
)
from o3de_pilot.core.upgrade import (
    upgrade_file,
    upgrade_directory,
    get_schema_version,
    needs_upgrade,
)

console = Console()


@click.group()
def manifest() -> None:
    """Manage the O3DE manifest."""
    pass


@manifest.command("resolve")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--no-save", is_flag=True, help="Don't save resolved manifest")
def resolve_command(as_json: bool, no_save: bool) -> None:
    """Resolve the manifest and discover all objects.
    
    Descends all registered paths, reads object JSON files,
    resolves children and dependencies, and saves to
    resolved_o3de_manifest.json.
    """
    manifest_path = get_manifest_path()
    
    if not manifest_path.exists():
        console.print(f"[red]Manifest not found:[/red] {manifest_path}")
        console.print("Run 'o3de-pilot init' to create a new manifest.")
        raise SystemExit(1)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Resolving manifest...", total=None)
        
        def on_progress(msg: str, current: int, total: int):
            progress.update(task, description=msg, completed=current, total=total)
        
        resolver = Resolver(manifest_path)
        resolver.resolve(progress_callback=on_progress)
        
        if not no_save:
            resolved_path = resolver.save()
            progress.update(task, description=f"Saved: {resolved_path}")
    
    if as_json:
        output = {
            "engines": len(resolver.engines),
            "projects": len(resolver.projects),
            "gems": len(resolver.gems),
            "templates": len(resolver.templates),
            "repos": len(resolver.repos),
            "overlays": len(resolver.overlays),
            "total": len(resolver.objects),
        }
        console.print_json(json.dumps(output))
    else:
        table = Table(title="Resolved Objects")
        table.add_column("Type", style="cyan")
        table.add_column("Count", style="green", justify="right")
        
        table.add_row("Engines", str(len(resolver.engines)))
        table.add_row("Projects", str(len(resolver.projects)))
        table.add_row("Gems", str(len(resolver.gems)))
        table.add_row("Templates", str(len(resolver.templates)))
        table.add_row("Repos", str(len(resolver.repos)))
        table.add_row("Overlays", str(len(resolver.overlays)))
        table.add_row("Total", str(len(resolver.objects)), style="bold")
        
        console.print(table)
        
        if not no_save:
            console.print(f"\n[dim]Saved:[/dim] {get_resolved_manifest_path()}")


@manifest.command("show")
@click.option("--resolved", is_flag=True, help="Show resolved manifest")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_command(resolved: bool, as_json: bool) -> None:
    """Show the manifest contents."""
    if resolved:
        path = get_resolved_manifest_path()
    else:
        path = get_manifest_path()
    
    if not path.exists():
        console.print(f"[red]Not found:[/red] {path}")
        raise SystemExit(1)
    
    with open(path) as f:
        data = json.load(f)
    
    if as_json:
        console.print_json(json.dumps(data, indent=2))
    else:
        # Pretty print summary
        console.print(f"[bold]Manifest:[/bold] {path}\n")
        
        if resolved:
            console.print(f"[dim]Resolved at:[/dim] {data.get('resolved_at', 'unknown')}")
            console.print(f"[dim]Objects:[/dim] {len(data.get('objects', {}))}")
        else:
            local = data.get("local", {})
            console.print("[bold]Local objects:[/bold]")
            for key in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
                paths = local.get(key, [])
                if paths:
                    console.print(f"  {key}: {len(paths)}")


@manifest.command("upgrade")
@click.argument("path", type=click.Path(exists=True), required=False)
@click.option("--recursive", "-r", is_flag=True, help="Upgrade recursively")
@click.option("--no-backup", is_flag=True, help="Don't create backups")
@click.option("--dry-run", is_flag=True, help="Show what would be upgraded")
def upgrade_command(
    path: str | None,
    recursive: bool,
    no_backup: bool,
    dry_run: bool,
) -> None:
    """Upgrade object JSON files to schema 2.0.0.
    
    Without PATH, upgrades the manifest and all registered objects.
    With PATH, upgrades the specified file or directory.
    """
    if path:
        target = Path(path)
    else:
        target = get_manifest_path()
    
    if not target.exists():
        console.print(f"[red]Not found:[/red] {target}")
        raise SystemExit(1)
    
    if target.is_file():
        # Single file upgrade
        with open(target) as f:
            data = json.load(f)
        
        obj_type, version = get_schema_version(data)
        
        if not needs_upgrade(data):
            console.print(f"[green]Already at latest schema:[/green] {target}")
            return
        
        if dry_run:
            console.print(f"[yellow]Would upgrade:[/yellow] {target} ({version} → 2.0.0)")
            return
        
        result = upgrade_file(target, backup=not no_backup)
        console.print(f"[green]Upgraded:[/green] {result[0]} ({result[1]} → {result[2]})")
    
    else:
        # Directory upgrade
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Scanning...", total=None)
            
            def on_progress(msg: str, current: int, total: int):
                progress.update(task, description=msg, completed=current, total=total)
            
            if dry_run:
                # Just scan and report
                json_files = list(target.rglob("*.json")) if recursive else list(target.glob("*.json"))
                upgradeable = []
                
                for json_file in json_files:
                    if json_file.name in ["engine.json", "project.json", "gem.json", "template.json", "repo.json", "overlay.json"]:
                        try:
                            with open(json_file) as f:
                                data = json.load(f)
                            if needs_upgrade(data):
                                _, version = get_schema_version(data)
                                upgradeable.append((json_file, version))
                        except Exception:
                            pass
                
                if upgradeable:
                    console.print(f"[yellow]Would upgrade {len(upgradeable)} files:[/yellow]")
                    for f, v in upgradeable[:20]:
                        console.print(f"  {f} ({v} → 2.0.0)")
                    if len(upgradeable) > 20:
                        console.print(f"  ... and {len(upgradeable) - 20} more")
                else:
                    console.print("[green]All files at latest schema.[/green]")
                return
            
            results = upgrade_directory(
                target,
                recursive=recursive,
                backup=not no_backup,
                progress_callback=on_progress,
            )
        
        if results:
            console.print(f"[green]Upgraded {len(results)} files:[/green]")
            for path, old_v, new_v in results[:10]:
                console.print(f"  {path.name} ({old_v} → {new_v})")
            if len(results) > 10:
                console.print(f"  ... and {len(results) - 10} more")
        else:
            console.print("[green]All files at latest schema.[/green]")


@manifest.command("add")
@click.argument("path", type=click.Path(exists=True))
@click.option("--type", "-t", "obj_type", 
              type=click.Choice(["engine", "project", "gem", "template", "repo", "overlay"]),
              help="Object type (auto-detected if not specified)")
def add_command(path: str, obj_type: str | None) -> None:
    """Add an object to the manifest.
    
    Registers the object at PATH in the local manifest.
    """
    target = Path(path).resolve()
    
    # Auto-detect type if not specified
    if not obj_type:
        for type_name in ["engine", "project", "gem", "template", "repo", "overlay"]:
            if (target / f"{type_name}.json").exists():
                obj_type = type_name
                break
        
        if not obj_type:
            console.print("[red]Could not detect object type.[/red]")
            console.print("Use --type to specify explicitly.")
            raise SystemExit(1)
    
    # Load manifest
    manifest_path = get_manifest_path()
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest_data = json.load(f)
    else:
        manifest_data = {
            "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "local": {},
            "remotes": [],
            "default": {},
        }
    
    # Add to manifest
    local = manifest_data.setdefault("local", {})
    type_list = local.setdefault(f"{obj_type}s", [])
    
    path_str = str(target)
    if path_str not in type_list:
        type_list.append(path_str)
        
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2)
        
        console.print(f"[green]Added {obj_type}:[/green] {target.name}")
    else:
        console.print(f"[yellow]Already registered:[/yellow] {target.name}")


@manifest.command("remove")
@click.argument("path", type=click.Path())
def remove_command(path: str) -> None:
    """Remove an object from the manifest.
    
    Unregisters the object. Does not delete files.
    """
    target = Path(path).resolve()
    manifest_path = get_manifest_path()
    
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)
    
    with open(manifest_path) as f:
        manifest_data = json.load(f)
    
    local = manifest_data.get("local", {})
    path_str = str(target)
    removed = False
    
    for type_list in local.values():
        if isinstance(type_list, list) and path_str in type_list:
            type_list.remove(path_str)
            removed = True
    
    if removed:
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2)
        console.print(f"[green]Removed:[/green] {target.name}")
    else:
        console.print(f"[yellow]Not found in manifest:[/yellow] {path}")
