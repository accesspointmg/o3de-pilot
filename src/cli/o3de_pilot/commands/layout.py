# O3DE Pilot CLI - Layout Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Layout management commands.

Layouts are symlinked build directories that combine:
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
    get_default_layouts_path,
    get_resolved_manifest_path,
    Resolver,
    get_manifest_path,
    ObjectType,
)
from o3de_pilot.core.layout import Layout, create_layout

console = Console()


@click.group()
def layout() -> None:
    """Manage build layouts.
    
    Layouts are symlinked directory structures that combine
    engine, project, gems, and overlays for building.
    """
    pass


@layout.command("create")
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
    """Create a new layout.
    
    Creates a symlinked directory structure combining the engine,
    project, and any specified overlays.
    
    Example:
        o3de-pilot layout create my-build -e ./o3de -p ./my-project
    """
    if not engine_path and not project_path:
        console.print("[red]Must specify --engine or --project (or both)[/red]")
        raise SystemExit(1)
    
    # Determine output path
    if output:
        output_path = Path(output).resolve()
    else:
        output_path = get_default_layouts_path() / name
    
    if output_path.exists():
        console.print(f"[red]Layout already exists:[/red] {output_path}")
        console.print("Use 'layout update' to update, or delete first.")
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
        task = progress.add_task("Creating layout...", total=None)
        
        layout_obj = create_layout(
            target_path=output_path,
            root_object_path=root_path,
            resolved_objects=resolved_objects,
            overlays=overlay_tuples,
        )
        
        # Save layout metadata
        import json
        from datetime import datetime
        meta = {
            "name": name,
            "created": datetime.now().isoformat(),
            "sources": [str(root_path)] + [str(p) for p in resolved_objects.values()],
            "overlays": [str(o[0]) for o in overlay_tuples],
        }
        meta_path = output_path / ".layout.json"
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)
        
        progress.update(task, description="Done")
    
    console.print(f"[green]Created layout:[/green] {output_path}")
    console.print(f"  Root: {root_path}")
    console.print(f"  Overlays: {len(overlay_tuples)}")


@layout.command("update")
@click.argument("name_or_path")
@click.option("--overlay", multiple=True, type=click.Path(exists=True),
              help="Additional overlay path")
def update_command(name_or_path: str, overlay: tuple[str, ...]) -> None:
    """Update an existing layout.
    
    Re-syncs symlinks and applies any new overlays.
    """
    # Find layout
    layout_path = Path(name_or_path)
    if not layout_path.exists():
        layout_path = get_default_layouts_path() / name_or_path
    
    if not layout_path.exists():
        console.print(f"[red]Layout not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    # Load layout metadata
    meta_path = layout_path / ".layout.json"
    if not meta_path.exists():
        console.print(f"[red]Not a valid layout:[/red] {layout_path}")
        console.print("Missing .layout.json metadata file.")
        raise SystemExit(1)
    
    with open(meta_path) as f:
        meta = json.load(f)
    
    # Reconstruct layout from metadata
    sources = [Path(p) for p in meta.get("sources", [])]
    existing_overlays = [Path(p) for p in meta.get("overlays", [])]
    new_overlays = [Path(o).resolve() for o in overlay]
    all_overlays = existing_overlays + new_overlays
    
    # Determine root object path and type
    root_source = sources[0] if sources else layout_path
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
        task = progress.add_task("Updating layout...", total=None)
        
        layout_obj = Layout(
            root_path=layout_path,
            root_object_path=root_source,
            root_object_type=root_type,
        )
        
        # Add resolved objects from sources
        for i, source in enumerate(sources):
            layout_obj.add_resolved_object(f"source_{i}", source)
        
        # Add overlays
        for i, overlay_path in enumerate(all_overlays):
            layout_obj.add_overlay(overlay_path, precedence=i)
        
        layout_obj.update()
        
        progress.update(task, description="Done")
    
    console.print(f"[green]Updated layout:[/green] {layout_path}")


@layout.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_command(as_json: bool) -> None:
    """List all layouts."""
    layouts_path = get_default_layouts_path()
    
    if not layouts_path.exists():
        if as_json:
            console.print_json("[]")
        else:
            console.print("[dim]No layouts found.[/dim]")
        return
    
    layouts = []
    for layout_dir in layouts_path.iterdir():
        if layout_dir.is_dir():
            meta_path = layout_dir / ".layout.json"
            if meta_path.exists():
                with open(meta_path) as f:
                    meta = json.load(f)
                layouts.append({
                    "name": meta.get("name", layout_dir.name),
                    "path": str(layout_dir),
                    "sources": meta.get("sources", []),
                    "overlays": meta.get("overlays", []),
                    "created": meta.get("created", ""),
                })
    
    if as_json:
        console.print_json(json.dumps(layouts))
    else:
        if not layouts:
            console.print("[dim]No layouts found.[/dim]")
            return
        
        table = Table(title="Layouts")
        table.add_column("Name", style="cyan")
        table.add_column("Sources", style="green", justify="right")
        table.add_column("Overlays", style="yellow", justify="right")
        table.add_column("Path", style="dim")
        
        for layout in layouts:
            table.add_row(
                layout["name"],
                str(len(layout["sources"])),
                str(len(layout["overlays"])),
                layout["path"],
            )
        
        console.print(table)


@layout.command("show")
@click.argument("name_or_path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_command(name_or_path: str, as_json: bool) -> None:
    """Show layout details."""
    # Find layout
    layout_path = Path(name_or_path)
    if not layout_path.exists():
        layout_path = get_default_layouts_path() / name_or_path
    
    if not layout_path.exists():
        console.print(f"[red]Layout not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    meta_path = layout_path / ".layout.json"
    if not meta_path.exists():
        console.print(f"[red]Not a valid layout:[/red] {layout_path}")
        raise SystemExit(1)
    
    with open(meta_path) as f:
        meta = json.load(f)
    
    if as_json:
        console.print_json(json.dumps(meta, indent=2))
    else:
        console.print(f"[bold]Layout:[/bold] {meta.get('name', layout_path.name)}")
        console.print(f"[dim]Path:[/dim] {layout_path}")
        console.print(f"[dim]Created:[/dim] {meta.get('created', 'unknown')}")
        
        console.print("\n[bold]Sources:[/bold]")
        for source in meta.get("sources", []):
            console.print(f"  • {source}")
        
        overlays = meta.get("overlays", [])
        if overlays:
            console.print("\n[bold]Overlays:[/bold]")
            for overlay in overlays:
                console.print(f"  • {overlay}")


@layout.command("delete")
@click.argument("name_or_path")
@click.option("--force", "-f", is_flag=True, help="Delete without confirmation")
def delete_command(name_or_path: str, force: bool) -> None:
    """Delete a layout.
    
    Removes the layout directory and all symlinks.
    Does not delete the original source files.
    """
    import shutil
    
    # Find layout
    layout_path = Path(name_or_path)
    if not layout_path.exists():
        layout_path = get_default_layouts_path() / name_or_path
    
    if not layout_path.exists():
        console.print(f"[red]Layout not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    if not force:
        if not click.confirm(f"Delete layout '{layout_path.name}'?"):
            console.print("[dim]Cancelled.[/dim]")
            return
    
    shutil.rmtree(layout_path)
    console.print(f"[green]Deleted:[/green] {layout_path}")


@layout.command("tree")
@click.argument("name_or_path")
@click.option("--depth", "-d", default=2, help="Tree depth")
def tree_command(name_or_path: str, depth: int) -> None:
    """Show layout directory tree."""
    # Find layout
    layout_path = Path(name_or_path)
    if not layout_path.exists():
        layout_path = get_default_layouts_path() / name_or_path
    
    if not layout_path.exists():
        console.print(f"[red]Layout not found:[/red] {name_or_path}")
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
    
    tree = Tree(f"[bold]{layout_path.name}[/bold]")
    add_tree_items(tree, layout_path, 0)
    console.print(tree)
