# O3DE Pilot CLI - Workspace Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Workspace management commands.

Workspaces are symlinked build directories that combine:
- Engine source
- Project source
- Gem sources
- Overlay customizations

This allows efficient builds without copying files.
"""

import click
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.tree import Tree

from o3de_pilot.core import (
    get_default_workspaces_path,
    get_resolved_manifest_path,
    Resolver,
    get_manifest_path,
    ObjectType,
)
from o3de_pilot.core.workspace import Workspace, create_workspace

console = Console()


@click.group()
def workspace() -> None:
    """Manage build workspaces.
    
    Workspaces are symlinked directory structures that combine
    engine, project, gems, and overlays for building.
    """
    pass


@workspace.command("create")
@click.argument("name")
@click.option("--engine", "-e", "engine_path", type=click.Path(exists=True), 
              help="Engine path")
@click.option("--project", "-p", "project_path", type=click.Path(exists=True),
              help="Project path")  
@click.option("--output", "-o", type=click.Path(), help="Output directory")
@click.option("--overlay", multiple=True, type=click.Path(exists=True),
              help="Overlay path (can be repeated)")
@click.option("--no-overlays", is_flag=True, help="Don't apply overlays")
def create_command(
    name: str,
    engine_path: str | None,
    project_path: str | None,
    output: str | None,
    overlay: tuple[str, ...],
    no_overlays: bool,
) -> None:
    """Create a new workspace.
    
    Creates a symlinked directory structure combining the engine,
    project, and any specified overlays.
    
    Example:
        o3de-pilot workspace create my-build -e ./o3de -p ./my-project
    """
    if not engine_path and not project_path:
        console.print("[red]Must specify --engine or --project (or both)[/red]")
        raise SystemExit(1)
    
    # Determine output path
    if output:
        output_path = Path(output).resolve()
    else:
        output_path = get_default_workspaces_path() / name
    
    if output_path.exists():
        console.print(f"[red]Workspace already exists:[/red] {output_path}")
        console.print("Use 'workspace update' to update, or delete first.")
        raise SystemExit(1)
    
    # Determine root object (engine or project)
    if engine_path:
        root_path = Path(engine_path).resolve()
    else:
        root_path = Path(project_path).resolve()
    
    # Collect additional resolved objects
    resolved_objects = {}
    if engine_path and project_path:
        # Both provided - project is secondary
        resolved_objects["_project_"] = Path(project_path).resolve()
    
    # Collect overlays with precedence
    overlay_tuples = [(Path(o).resolve(), i) for i, o in enumerate(overlay)] if not no_overlays else []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Creating workspace...", total=None)
        
        workspace_obj = create_workspace(
            target_path=output_path,
            root_object_path=root_path,
            resolved_objects=resolved_objects,
            overlays=overlay_tuples,
        )
        
        # Save workspace metadata
        import json
        from datetime import datetime
        meta = {
            "name": name,
            "created": datetime.now().isoformat(),
            "sources": [str(root_path)] + [str(p) for p in resolved_objects.values()],
            "overlays": [str(o[0]) for o in overlay_tuples],
        }
        meta_path = output_path / ".workspace.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        
        progress.update(task, description="Done")
    
    console.print(f"[green]Created workspace:[/green] {output_path}")
    console.print(f"  Root: {root_path}")
    console.print(f"  Overlays: {len(overlay_tuples)}")


@workspace.command("update")
@click.argument("name_or_path")
@click.option("--overlay", multiple=True, type=click.Path(exists=True),
              help="Additional overlay path")
def update_command(name_or_path: str, overlay: tuple[str, ...]) -> None:
    """Update an existing workspace.
    
    Re-syncs symlinks and applies any new overlays.
    """
    # Find workspace
    workspace_path = Path(name_or_path)
    if not workspace_path.exists():
        workspace_path = get_default_workspaces_path() / name_or_path
    
    if not workspace_path.exists():
        console.print(f"[red]Workspace not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    # Load workspace metadata
    meta_path = workspace_path / ".workspace.json"
    if not meta_path.exists():
        console.print(f"[red]Not a valid workspace:[/red] {workspace_path}")
        console.print("Missing .workspace.json metadata file.")
        raise SystemExit(1)
    
    with open(meta_path) as f:
        meta = json.load(f)
    
    # Reconstruct workspace from metadata
    sources = [Path(p) for p in meta.get("sources", [])]
    existing_overlays = [Path(p) for p in meta.get("overlays", [])]
    new_overlays = [Path(o).resolve() for o in overlay]
    all_overlays = existing_overlays + new_overlays
    
    # Determine root object path and type
    root_source = sources[0] if sources else workspace_path
    if (root_source / "engine.json").exists():
        root_type = ObjectType.ENGINE
    elif (root_source / "project.json").exists():
        root_type = ObjectType.PROJECT
    else:
        root_type = ObjectType.ENGINE  # fallback
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Updating workspace...", total=None)
        
        workspace_obj = Workspace(
            root_path=workspace_path,
            root_object_path=root_source,
            root_object_type=root_type,
        )
        
        # Add resolved objects from sources
        for i, source in enumerate(sources):
            workspace_obj.add_resolved_object(f"source_{i}", source)
        
        # Add overlays
        for i, overlay_path in enumerate(all_overlays):
            workspace_obj.add_overlay(overlay_path, precedence=i)
        
        workspace_obj.update()
        
        progress.update(task, description="Done")
    
    console.print(f"[green]Updated workspace:[/green] {workspace_path}")


@workspace.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_command(as_json: bool) -> None:
    """List all workspaces."""
    workspaces_path = get_default_workspaces_path()
    
    if not workspaces_path.exists():
        if as_json:
            console.print_json("[]")
        else:
            console.print("[dim]No workspaces found.[/dim]")
        return
    
    workspaces = []
    for ws_dir in workspaces_path.iterdir():
        if ws_dir.is_dir():
            meta_path = ws_dir / ".workspace.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)
                workspaces.append({
                    "name": meta.get("name", ws_dir.name),
                    "path": str(ws_dir),
                    "sources": meta.get("sources", []),
                    "overlays": meta.get("overlays", []),
                    "created": meta.get("created", ""),
                })
    
    if as_json:
        console.print_json(json.dumps(workspaces))
    else:
        if not workspaces:
            console.print("[dim]No workspaces found.[/dim]")
            return
        
        table = Table(title="Workspaces")
        table.add_column("Name", style="cyan")
        table.add_column("Sources", style="green", justify="right")
        table.add_column("Overlays", style="yellow", justify="right")
        table.add_column("Path", style="dim")
        
        for ws in workspaces:
            table.add_row(
                ws["name"],
                str(len(ws["sources"])),
                str(len(ws["overlays"])),
                ws["path"],
            )
        
        console.print(table)


@workspace.command("show")
@click.argument("name_or_path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_command(name_or_path: str, as_json: bool) -> None:
    """Show workspace details."""
    # Find workspace
    ws_path = Path(name_or_path)
    if not ws_path.exists():
        ws_path = get_default_workspaces_path() / name_or_path
    
    if not ws_path.exists():
        console.print(f"[red]Workspace not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    meta_path = ws_path / ".workspace.json"
    if not meta_path.exists():
        console.print(f"[red]Not a valid workspace:[/red] {ws_path}")
        raise SystemExit(1)
    
    with open(meta_path) as f:
        meta = json.load(f)
    
    if as_json:
        console.print_json(json.dumps(meta, indent=2))
    else:
        console.print(f"[bold]Workspace:[/bold] {meta.get('name', ws_path.name)}")
        console.print(f"[dim]Path:[/dim] {ws_path}")
        console.print(f"[dim]Created:[/dim] {meta.get('created', 'unknown')}")
        
        console.print("\n[bold]Sources:[/bold]")
        for source in meta.get("sources", []):
            console.print(f"  • {source}")
        
        overlays = meta.get("overlays", [])
        if overlays:
            console.print("\n[bold]Overlays:[/bold]")
            for overlay in overlays:
                console.print(f"  • {overlay}")


@workspace.command("delete")
@click.argument("name_or_path")
@click.option("--force", "-f", is_flag=True, help="Delete without confirmation")
def delete_command(name_or_path: str, force: bool) -> None:
    """Delete a workspace.
    
    Removes the workspace directory and all symlinks.
    Does not delete the original source files.
    """
    import shutil
    
    # Find workspace
    ws_path = Path(name_or_path)
    if not ws_path.exists():
        ws_path = get_default_workspaces_path() / name_or_path
    
    if not ws_path.exists():
        console.print(f"[red]Workspace not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    if not force:
        if not click.confirm(f"Delete workspace '{ws_path.name}'?"):
            console.print("[dim]Cancelled.[/dim]")
            return
    
    shutil.rmtree(ws_path)
    console.print(f"[green]Deleted:[/green] {ws_path}")


@workspace.command("tree")
@click.argument("name_or_path")
@click.option("--depth", "-d", default=2, help="Tree depth")
def tree_command(name_or_path: str, depth: int) -> None:
    """Show workspace directory tree."""
    # Find workspace
    ws_path = Path(name_or_path)
    if not ws_path.exists():
        ws_path = get_default_workspaces_path() / name_or_path
    
    if not ws_path.exists():
        console.print(f"[red]Workspace not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    def add_tree_items(tree: Tree, path: Path, current_depth: int):
        if current_depth >= depth:
            return
        
        try:
            items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        
        for item in items:
            if item.name.startswith("."):
                continue
            
            if item.is_symlink():
                target = item.resolve()
                subtree = tree.add(f"[cyan]{item.name}[/cyan] → [dim]{target}[/dim]")
            elif item.is_dir():
                subtree = tree.add(f"[bold blue]{item.name}/[/bold blue]")
                add_tree_items(subtree, item, current_depth + 1)
            else:
                tree.add(item.name)
    
    tree = Tree(f"[bold]{ws_path.name}[/bold]")
    add_tree_items(tree, ws_path, 0)
    console.print(tree)
