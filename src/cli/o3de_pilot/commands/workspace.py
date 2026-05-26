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
from datetime import datetime
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
from o3de_pilot.core.models import WorkspaceHeader, WorkspaceMeta, SCHEMA_VERSION, SCHEMA_BASE_URL
from o3de_pilot.core.solver import (
    solve_for_workspace,
    SolveResult,
    CandidateStatus,
)

console = Console()

# Workspace metadata filename (visible, standard pattern)
WORKSPACE_META = "workspace.json"
# Legacy hidden filename for fallback reads
_LEGACY_WORKSPACE_META = ".workspace.json"


def _find_workspace_meta(ws_path: Path) -> Path | None:
    """Find workspace metadata file, preferring new name with legacy fallback."""
    meta = ws_path / WORKSPACE_META
    if meta.exists():
        return meta
    legacy = ws_path / _LEGACY_WORKSPACE_META
    if legacy.exists():
        return legacy
    return None


def _read_workspace_meta(ws_path: Path) -> WorkspaceMeta | None:
    """Read and validate workspace metadata via Pydantic model.

    Handles legacy `.workspace.json` files that lack `$schema`,
    `$schemaVersion`, and `workspace` header by injecting defaults.
    """
    meta_path = _find_workspace_meta(ws_path)
    if meta_path is None:
        return None
    with open(meta_path) as f:
        data = json.load(f)
    # Inject defaults for legacy files missing required fields
    if "$schema" not in data:
        data["$schema"] = f"{SCHEMA_BASE_URL}/o3de-workspace-{SCHEMA_VERSION}.json"
    if "$schemaVersion" not in data:
        data["$schemaVersion"] = SCHEMA_VERSION
    if "workspace" not in data:
        data["workspace"] = {"name": data.get("name", ws_path.name)}
    if "created" not in data:
        data["created"] = ""
    return WorkspaceMeta.model_validate(data)


def _write_workspace_meta(ws_path: Path, meta: WorkspaceMeta) -> None:
    """Write workspace metadata as workspace.json."""
    meta_path = ws_path / WORKSPACE_META
    with open(meta_path, "w") as f:
        json.dump(meta.model_dump(by_alias=True, exclude_none=True), f, indent=2)


def _build_workspace_meta(
    name: str,
    root_path: Path,
    root_type: str,
    sources: list[str],
    overlays: list[str],
    file_owners: dict[str, str] | None = None,
) -> WorkspaceMeta:
    """Build a WorkspaceMeta model for a new workspace."""
    return WorkspaceMeta.model_validate({
        "$schema": f"{SCHEMA_BASE_URL}/o3de-workspace-{SCHEMA_VERSION}.json",
        "$schemaVersion": SCHEMA_VERSION,
        "workspace": {"name": name},
        "created": datetime.now().isoformat(),
        "root_object": str(root_path),
        "root_type": root_type,
        "sources": sources,
        "overlays": overlays,
        "file_owners": file_owners or {},
    })


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
        
        # Determine root type string
        if (root_path / "engine.json").exists():
            root_type_str = "engine"
        elif (root_path / "project.json").exists():
            root_type_str = "project"
        else:
            root_type_str = "engine"
        
        # Save workspace metadata via Pydantic model
        meta = _build_workspace_meta(
            name=name,
            root_path=root_path,
            root_type=root_type_str,
            sources=[str(root_path)] + [str(p) for p in resolved_objects.values()],
            overlays=[str(o[0]) for o in overlay_tuples],
            file_owners=workspace_obj.file_owners,
        )
        _write_workspace_meta(output_path, meta)
        
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
    meta = _read_workspace_meta(workspace_path)
    if meta is None:
        console.print(f"[red]Not a valid workspace:[/red] {workspace_path}")
        console.print("Missing workspace.json metadata file.")
        raise SystemExit(1)
    
    # Reconstruct workspace from metadata
    sources = [Path(p) for p in meta.sources]
    existing_overlays = [Path(p) for p in meta.overlays]
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
            meta = _read_workspace_meta(ws_dir)
            if meta is not None:
                workspaces.append({
                    "name": meta.workspace.name or ws_dir.name,
                    "path": str(ws_dir),
                    "sources": meta.sources,
                    "overlays": meta.overlays,
                    "created": meta.created,
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
    
    meta = _read_workspace_meta(ws_path)
    if meta is None:
        console.print(f"[red]Not a valid workspace:[/red] {ws_path}")
        raise SystemExit(1)
    
    if as_json:
        console.print_json(json.dumps(
            meta.model_dump(by_alias=True, exclude_none=True), indent=2
        ))
    else:
        console.print(f"[bold]Workspace:[/bold] {meta.workspace.name or ws_path.name}")
        console.print(f"[dim]Path:[/dim] {ws_path}")
        console.print(f"[dim]Created:[/dim] {meta.created}")
        
        console.print("\n[bold]Sources:[/bold]")
        for source in meta.sources:
            console.print(f"  • {source}")
        
        if meta.overlays:
            console.print("\n[bold]Overlays:[/bold]")
            for ov in meta.overlays:
                console.print(f"  • {ov}")


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


@workspace.command("solve")
@click.argument("root_name")
@click.option("--include-store", is_flag=True, help="Include remote store objects")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--dry-run", is_flag=True, help="Show what would be resolved")
def solve_command(
    root_name: str,
    include_store: bool,
    as_json: bool,
    dry_run: bool,
) -> None:
    """Solve dependencies for a workspace root object.

    Resolves the full transitive dependency graph for ROOT_NAME
    (an engine or project registered in the manifest), showing
    which objects are local, remote, or unknown.

    Example:
        o3de-pilot workspace solve org.o3de.engine.o3de
        o3de-pilot workspace solve org.o3de.project.myproject --include-store
    """
    from o3de_pilot.core.store import Store

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Resolving manifest...", total=None)

        resolver = Resolver()
        resolver.resolve()

        store = None
        if include_store:
            progress.update(task, description="Refreshing store...")
            store = Store()
            store.refresh_sync(resolver.manifest_remotes)

        progress.update(task, description="Solving dependencies...")

        def on_progress(msg: str) -> None:
            progress.update(task, description=msg)

        result = solve_for_workspace(
            root_name=root_name,
            resolver=resolver,
            store=store,
            progress_callback=on_progress,
        )

        progress.update(task, description="Done")

    if as_json:
        import json as json_mod
        data = {
            "root": result.root_name,
            "root_version": result.root_version,
            "resolved": result.is_resolved,
            "conflict": result.conflict_message or None,
            "candidates": {
                name: {
                    "version": c.version,
                    "type": c.object_type.value,
                    "status": c.status.value,
                    "path": str(c.path) if c.path else None,
                }
                for name, c in result.candidates.items()
            },
            "children": {
                name: {
                    "version": c.version,
                    "type": c.object_type.value,
                    "path": str(c.path) if c.path else None,
                }
                for name, c in result.children.items()
            },
            "overlays": {
                base: [
                    {
                        "name": o.name,
                        "version": o.version,
                        "precedence": o.precedence,
                    }
                    for o in entries
                ]
                for base, entries in result.overlays.items()
            },
        }
        console.print_json(json_mod.dumps(data, indent=2))
        return

    if not result.is_resolved:
        console.print(f"[red]Resolution failed:[/red] {result.conflict_message}")
        raise SystemExit(1)

    console.print(f"[bold]Workspace: {result.root_name}@{result.root_version}[/bold]")
    console.print()

    # Build table
    table = Table(title="Resolved Dependencies")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Path", style="dim")

    status_style = {
        CandidateStatus.LOCAL: "green",
        CandidateStatus.REMOTE: "blue",
        CandidateStatus.UNKNOWN: "red",
    }

    for name, cand in sorted(result.candidates.items()):
        style = status_style.get(cand.status, "white")
        table.add_row(
            name,
            cand.version,
            cand.object_type.value,
            f"[{style}]{cand.status.value}[/{style}]",
            str(cand.path) if cand.path else "",
        )

    console.print(table)

    # Contained objects (not dependencies)
    if result.children:
        console.print()
        console.print(f"[dim]Contained objects ({len(result.children)}):[/dim]")
        for name, cand in sorted(result.children.items()):
            console.print(f"  [dim]{name}@{cand.version} ({cand.object_type.value})[/dim]")

    # Overlays
    if result.overlays:
        console.print()
        console.print("[bold]Overlays:[/bold]")
        for base_name, entries in result.overlays.items():
            console.print(f"  [cyan]{base_name}[/cyan]:")
            for entry in entries:
                console.print(
                    f"    {entry.name}@{entry.version} "
                    f"(precedence {entry.precedence})"
                )

    console.print()
    console.print(
        f"  [green]{result.local_count} local[/green]  "
        f"[blue]{result.remote_count} remote[/blue]  "
        f"[red]{result.unknown_count} unknown[/red]"
    )
