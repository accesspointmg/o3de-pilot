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
import subprocess
import sys
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
from o3de_pilot.core.workspace import Workspace, create_workspace, detect_root_type
from o3de_pilot.core.models import (
    WorkspaceHeader,
    WorkspaceMeta,
    ResolvedCandidate,
    SCHEMA_VERSION,
    SCHEMA_BASE_URL,
)
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


def _register_workspace(ws_path: Path) -> None:
    """Register a workspace path in the global manifest."""
    manifest_path = get_manifest_path()
    with open(manifest_path) as f:
        manifest = json.load(f)
    workspaces = manifest.setdefault("workspaces", [])
    path_str = ws_path.resolve().as_posix()
    if path_str not in workspaces:
        workspaces.append(path_str)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)


def _unregister_workspace(ws_path: Path) -> None:
    """Remove a workspace path from the global manifest."""
    manifest_path = get_manifest_path()
    with open(manifest_path) as f:
        manifest = json.load(f)
    workspaces = manifest.get("workspaces", [])
    path_str = ws_path.resolve().as_posix()
    if path_str in workspaces:
        workspaces.remove(path_str)
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)


def _get_registered_workspaces() -> list[Path]:
    """Return all workspace paths registered in the manifest."""
    manifest_path = get_manifest_path()
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    return [Path(p) for p in manifest.get("workspaces", [])]


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
    resolved_candidates: list[dict] | None = None,
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
        "resolved_candidates": resolved_candidates or [],
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
@click.option("--no-solve", is_flag=True,
              help="Skip dependency resolution — only use explicitly provided paths")
@click.option("--include-store", is_flag=True,
              help="Include remote store when resolving dependencies")
@click.option("--auto-install", "-y", is_flag=True,
              help="Automatically download and install missing remote dependencies")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def create_command(
    name: str,
    engine_path: str | None,
    project_path: str | None,
    output: str | None,
    overlay: tuple[str, ...],
    no_overlays: bool,
    no_solve: bool,
    include_store: bool,
    auto_install: bool,
    as_json: bool,
) -> None:
    """Create a new workspace.
    
    Creates a structured workspace with symlinked files organised by
    object type (Engines/, Projects/, Gems/, etc.).

    By default, runs the dependency solver to resolve all transitive
    dependencies from the manifest.  Use --no-solve for explicit-only mode.
    
    Example:
        o3de-pilot workspace create my-build -e ./o3de -p ./my-project
        o3de-pilot workspace create my-build -e ./o3de -p ./my-project --no-solve
    """
    if not engine_path and not project_path:
        if as_json:
            from o3de_pilot.core.json_output import emit_error
            emit_error("Must specify --engine or --project (or both)", code="E_INVALID_ARGS")
        else:
            console.print("[red]Must specify --engine or --project (or both)[/red]")
        raise SystemExit(1)
    
    # Determine output path
    if output:
        output_path = Path(output).resolve() / name
    else:
        output_path = get_default_workspaces_path() / name
    
    if output_path.exists():
        if as_json:
            from o3de_pilot.core.json_output import emit_error
            emit_error(f"Workspace already exists: {output_path}", code="E_WS_EXISTS")
        else:
            console.print(f"[red]Workspace already exists:[/red] {output_path}")
            console.print("Use 'workspace update' to update, or delete first.")
        raise SystemExit(1)
    
    # Determine root object
    if engine_path:
        root_path = Path(engine_path).resolve()
        root_type = detect_root_type(root_path)
    elif project_path:
        root_path = Path(project_path).resolve()
        root_type = detect_root_type(root_path)
    else:
        root_path = Path(engine_path).resolve()
        root_type = ObjectType.ENGINE
    
    root_type_str = root_type.value
    
    # Build resolved_objects: name → (path, ObjectType)
    resolved_objects: dict[str, tuple[Path, ObjectType]] = {}
    solve_result: SolveResult | None = None
    
    if engine_path and project_path:
        # Both provided — secondary goes in too
        proj_path = Path(project_path).resolve()
        resolved_objects[proj_path.name] = (proj_path, ObjectType.PROJECT)
    
    # Collect overlays with precedence
    overlay_tuples = [(Path(o).resolve(), i, None) for i, o in enumerate(overlay)] if not no_overlays else []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        # ------------------------------------------------------------------
        # Phase 1: Dependency resolution (unless --no-solve)
        # ------------------------------------------------------------------
        if not no_solve:
            task = progress.add_task("Resolving manifest...", total=None)

            resolver = Resolver()
            resolver.resolve()

            store = None
            if include_store:
                from o3de_pilot.core.store import Store

                progress.update(task, description="Refreshing store...")
                store = Store()
                store.refresh_sync(resolver.manifest_remotes)

            progress.update(task, description="Solving dependencies...")

            # Determine the root object name in the manifest
            root_name = root_path.name
            # Try to find a better name from the resolver's object index
            for obj_name, obj in resolver.objects.items():
                if obj.path and obj.path.resolve() == root_path:
                    root_name = obj_name
                    break

            # Only run the solver if the root is known to the resolver
            # (i.e. registered in the manifest).  If the user points at a
            # path that hasn't been registered yet, skip solving — the
            # explicit --engine / --project paths are sufficient.
            if root_name in resolver.objects:
                def on_progress(msg: str) -> None:
                    progress.update(task, description=msg)

                solve_result = solve_for_workspace(
                    root_name=root_name,
                    resolver=resolver,
                    store=store,
                    progress_callback=on_progress,
                )

                if not solve_result.is_resolved:
                    progress.stop()
                    console.print(
                        f"[red]Dependency resolution failed:[/red] "
                        f"{solve_result.conflict_message}"
                    )
                    raise SystemExit(1)

                # Convert solved candidates + children → resolved_objects
                # (only LOCAL candidates can be assembled into the workspace)
                for cand_name, cand in solve_result.candidates.items():
                    if cand.status == CandidateStatus.LOCAL and cand.path:
                        if cand.path.resolve() == root_path:
                            continue  # Root is added by create_workspace itself
                        resolved_objects[cand_name] = (cand.path, cand.object_type)

                for child_name, child in solve_result.children.items():
                    if child.status == CandidateStatus.LOCAL and child.path:
                        if child.path.resolve() == root_path:
                            continue
                        resolved_objects[child_name] = (child.path, child.object_type)

                # Add solved overlays (unless --no-overlays)
                if not no_overlays:
                    for _base, entries in solve_result.overlays.items():
                        for ov in entries:
                            if ov.path and ov.status == CandidateStatus.LOCAL:
                                # Avoid duplicating explicitly-provided overlays
                                ov_resolved = ov.path.resolve()
                                if not any(p.resolve() == ov_resolved for p, *_ in overlay_tuples):
                                    overlay_tuples.append((ov_resolved, ov.precedence, ov.extends))

                # Report remote/unknown candidates
                remote_count = solve_result.remote_count
                unknown_count = solve_result.unknown_count

                # ----------------------------------------------------------
                # J2: Auto-install missing remote dependencies
                # ----------------------------------------------------------
                if remote_count and auto_install and store:
                    progress.update(task, description="Installing remote dependencies...")

                    def on_install_progress(msg: str, current: int, total: int) -> None:
                        progress.update(task, description=msg)

                    installed = resolver.auto_install_missing(
                        store=store,
                        confirm=True,
                        progress_callback=on_install_progress,
                    )

                    if installed:
                        console.print(
                            f"[green]Installed {len(installed)} remote dependencies[/green]"
                        )
                        # Re-resolve and re-solve to pick up newly-local objects
                        progress.update(task, description="Re-resolving after install...")
                        resolver.resolve()

                        progress.update(task, description="Re-solving dependencies...")
                        solve_result = solve_for_workspace(
                            root_name=root_name,
                            resolver=resolver,
                            store=store,
                            progress_callback=on_progress,
                        )

                        if not solve_result.is_resolved:
                            progress.stop()
                            console.print(
                                f"[red]Re-solve after install failed:[/red] "
                                f"{solve_result.conflict_message}"
                            )
                            raise SystemExit(1)

                        # Rebuild resolved_objects from the fresh solve
                        resolved_objects.clear()
                        if engine_path and project_path:
                            proj_path = Path(project_path).resolve()
                            resolved_objects[proj_path.name] = (proj_path, ObjectType.PROJECT)

                        for cand_name, cand in solve_result.candidates.items():
                            if cand.status == CandidateStatus.LOCAL and cand.path:
                                if cand.path.resolve() == root_path:
                                    continue
                                resolved_objects[cand_name] = (cand.path, cand.object_type)

                        for child_name, child in solve_result.children.items():
                            if child.status == CandidateStatus.LOCAL and child.path:
                                if child.path.resolve() == root_path:
                                    continue
                                resolved_objects[child_name] = (child.path, child.object_type)

                        # Re-process overlays
                        if not no_overlays:
                            overlay_tuples = [(Path(o).resolve(), i, None) for i, o in enumerate(overlay)]
                            for _base, entries in solve_result.overlays.items():
                                for ov in entries:
                                    if ov.path and ov.status == CandidateStatus.LOCAL:
                                        ov_resolved = ov.path.resolve()
                                        if not any(p.resolve() == ov_resolved for p, *_ in overlay_tuples):
                                            overlay_tuples.append((ov_resolved, ov.precedence, ov.extends))

                        # Update counts after re-solve
                        remote_count = solve_result.remote_count
                        unknown_count = solve_result.unknown_count

                elif remote_count and auto_install and not store:
                    progress.stop()
                    console.print(
                        "[yellow]⚠ --auto-install requires --include-store[/yellow]"
                    )
                    progress.start()

                if remote_count or unknown_count:
                    progress.stop()
                    if remote_count:
                        console.print(
                            f"[yellow]⚠ {remote_count} remote dependencies not yet "
                            f"installed — run 'workspace solve {root_name} "
                            f"--include-store' for details[/yellow]"
                        )
                    if unknown_count:
                        console.print(
                            f"[red]⚠ {unknown_count} dependencies could not be "
                            f"found anywhere[/red]"
                        )
                    progress.start()
            else:
                console.print(
                    f"[dim]Root object not registered in manifest — "
                    f"skipping dependency resolution[/dim]"
                )
                progress.start()

            progress.update(task, description="Dependencies resolved")

        # ------------------------------------------------------------------
        # Phase 2: Assemble the workspace
        # ------------------------------------------------------------------
        task2 = progress.add_task("Creating workspace...", total=None)
        
        workspace_obj = create_workspace(
            target_path=output_path,
            root_object_path=root_path,
            resolved_objects=resolved_objects,
            overlays=overlay_tuples,
        )
        
        # Save workspace metadata via Pydantic model
        sources = [str(root_path)]
        sources += [str(p) for p, _t in resolved_objects.values()]

        # Build resolved_candidates from solve result
        candidates_data: list[dict] = []
        if solve_result:
            all_cands = {**solve_result.candidates, **solve_result.children}
            for cand_name, cand in all_cands.items():
                candidates_data.append({
                    "name": cand_name,
                    "version": cand.version,
                    "object_type": cand.object_type.value if hasattr(cand.object_type, "value") else str(cand.object_type),
                    "status": cand.status.value if hasattr(cand.status, "value") else str(cand.status),
                    "path": str(cand.path) if cand.path else None,
                })

        meta = _build_workspace_meta(
            name=name,
            root_path=root_path,
            root_type=root_type_str,
            sources=sources,
            overlays=[str(o[0]) for o in overlay_tuples],
            file_owners=workspace_obj.file_owners,
            resolved_candidates=candidates_data,
        )
        _write_workspace_meta(output_path, meta)
        
        progress.update(task2, description="Done")
    
    _register_workspace(output_path)

    if as_json:
        from o3de_pilot.core.json_output import emit_response
        data = {
            "action": "created",
            "workspace": str(output_path),
            "root": str(root_path),
            "objects": len(resolved_objects) + 1,
            "overlays": len(overlay_tuples),
        }
        if solve_result:
            data["resolved_local"] = solve_result.local_count
            data["resolved_remote"] = solve_result.remote_count
        emit_response(data=data)
    else:
        console.print(f"[green]Created workspace:[/green] {output_path}")
        console.print(f"  Root: {root_path}")
        console.print(f"  Objects: {len(resolved_objects) + 1}")
        if solve_result:
            console.print(f"  Resolved: {solve_result.local_count} local")
            if solve_result.remote_count:
                console.print(f"  Remote (not installed): {solve_result.remote_count}")
        console.print(f"  Overlays: {len(overlay_tuples)}")


@workspace.command("update")
@click.argument("name_or_path")
@click.option("--overlay", multiple=True, type=click.Path(exists=True),
              help="Additional overlay path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def update_command(name_or_path: str, overlay: tuple[str, ...], as_json: bool) -> None:
    """Update an existing workspace.
    
    Re-syncs symlinks and applies any new overlays.
    """
    from o3de_pilot.core.json_output import emit_response, emit_error
    
    # Find workspace
    workspace_path = Path(name_or_path)
    if not workspace_path.exists():
        workspace_path = get_default_workspaces_path() / name_or_path
    
    if not workspace_path.exists():
        if as_json:
            emit_error(f"Workspace not found: {name_or_path}", code="E_WS_NOT_FOUND")
        else:
            console.print(f"[red]Workspace not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    # Load workspace metadata
    meta = _read_workspace_meta(workspace_path)
    if meta is None:
        if as_json:
            emit_error(f"Not a valid workspace: {workspace_path}", code="E_WS_INVALID")
        else:
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
    try:
        root_type = detect_root_type(root_source)
    except Exception:
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
        
        # Add resolved objects from sources with their types
        for i, source in enumerate(sources):
            if (source / "engine.json").exists():
                stype = ObjectType.ENGINE
            elif (source / "project.json").exists():
                stype = ObjectType.PROJECT
            elif (source / "gem.json").exists():
                stype = ObjectType.GEM
            else:
                stype = ObjectType.GEM
            workspace_obj.add_resolved_object(source.name, source, stype)
        
        # Add overlays
        for i, overlay_path in enumerate(all_overlays):
            workspace_obj.add_overlay(overlay_path, precedence=i)
        
        workspace_obj.update()
        
        progress.update(task, description="Done")
    
    if as_json:
        emit_response(data={
            "action": "updated",
            "workspace": str(workspace_path),
            "overlays": len(all_overlays),
        })
    else:
        console.print(f"[green]Updated workspace:[/green] {workspace_path}")


@workspace.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_command(as_json: bool) -> None:
    """List all workspaces."""
    # Collect workspace dirs from default folder + manifest-registered paths
    seen: set[Path] = set()
    ws_dirs: list[Path] = []

    workspaces_path = get_default_workspaces_path()
    if workspaces_path.exists():
        for d in workspaces_path.iterdir():
            if d.is_dir():
                resolved = d.resolve()
                if resolved not in seen:
                    seen.add(resolved)
                    ws_dirs.append(d)

    for rp in _get_registered_workspaces():
        if rp.is_dir():
            resolved = rp.resolve()
            if resolved not in seen:
                seen.add(resolved)
                ws_dirs.append(rp)

    workspaces = []
    for ws_dir in ws_dirs:
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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
def delete_command(name_or_path: str, force: bool, as_json: bool, dry_run: bool) -> None:
    """Delete a workspace.
    
    Removes the workspace directory and all symlinks.
    Does not delete the original source files.
    """
    import shutil
    from o3de_pilot.core.json_output import emit_response, emit_error
    
    # Find workspace
    ws_path = Path(name_or_path)
    if not ws_path.exists():
        ws_path = get_default_workspaces_path() / name_or_path
    
    if not ws_path.exists():
        if as_json:
            emit_error(f"Workspace not found: {name_or_path}", code="E_WS_NOT_FOUND")
        else:
            console.print(f"[red]Workspace not found:[/red] {name_or_path}")
        raise SystemExit(1)
    
    if dry_run:
        if as_json:
            emit_response(data={
                "dry_run": True,
                "action": "delete",
                "workspace": str(ws_path),
            })
        else:
            console.print(f"[dim]Would delete:[/dim] {ws_path}")
        return
    
    if not force:
        if not click.confirm(f"Delete workspace '{ws_path.name}'?"):
            console.print("[dim]Cancelled.[/dim]")
            return
    
    shutil.rmtree(ws_path)
    _unregister_workspace(ws_path)
    if as_json:
        emit_response(data={"action": "deleted", "workspace": str(ws_path)})
    else:
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


# ---------------------------------------------------------------------------
# workspace build
# ---------------------------------------------------------------------------

def _find_third_party_path(
    meta: WorkspaceMeta | None = None,
    engine_path: Path | None = None,
) -> Path | None:
    """Resolve LY_3RDPARTY_PATH via the full resolution chain.

    Resolution order:
    1. Workspace metadata (``meta.third_party_path``)
    2. Engine settings (``engine.json`` / ``engine.2-0-0.json``)
    3. User config (``~/.o3de/pilot/config.yaml`` ``build.third_party_path``)
    4. Manifest default (``o3de_manifest.json`` ``default.third_party_path``)
    5. Default path (``~/.o3de/3rdParty``)

    Returns the first existing path, or ``None``.
    """
    candidates: list[str] = []

    # 1. Workspace metadata
    if meta is not None:
        ws_tp = getattr(meta, "third_party_path", None)
        if ws_tp:
            candidates.append(ws_tp)

    # 2. Engine settings
    if engine_path is not None:
        for name in ("engine.2-0-0.json", "engine.json"):
            ej = engine_path / name
            if ej.exists():
                try:
                    edata = json.loads(ej.read_text())
                    nested = edata.get("engine", edata)
                    tp = nested.get("third_party_path", "")
                    if tp:
                        candidates.append(tp)
                except Exception:
                    pass
                break

    # 3. User config
    try:
        from o3de_pilot.core.config import get_config
        cfg = get_config()
        cfg_tp = cfg.get("build.third_party_path")
        if cfg_tp:
            candidates.append(str(cfg_tp))
    except Exception:
        pass

    # 4. Manifest default
    try:
        manifest_path = get_manifest_path()
        if manifest_path and manifest_path.exists():
            data = json.loads(manifest_path.read_text())
            tp = data.get("default", {}).get("third_party_path", "")
            if tp:
                candidates.append(tp)
    except Exception:
        pass

    # 5. Default path (~/.o3de/3rdParty)
    from o3de_pilot.core.paths import get_third_party_path
    candidates.append(str(get_third_party_path()))

    for tp_str in candidates:
        p = Path(tp_str)
        if p.exists():
            return p
    return None


def _find_engine_path(meta: WorkspaceMeta) -> Path | None:
    """Find the engine path from workspace metadata."""
    # Check resolved_candidates for an engine
    for cand in meta.resolved_candidates:
        if cand.object_type == "engine" and cand.path:
            return Path(cand.path)
    # Fallback: if root_type is engine, use root_object
    if meta.root_type == "engine" and meta.root_object:
        return Path(meta.root_object)
    return None


def _find_project_path(meta: WorkspaceMeta) -> Path | None:
    """Find the project path from workspace metadata."""
    # Check resolved_candidates for a project
    for cand in meta.resolved_candidates:
        if cand.object_type == "project" and cand.path:
            return Path(cand.path)
    # Fallback: if root_type is project, use root_object
    if meta.root_type == "project" and meta.root_object:
        return Path(meta.root_object)
    return None


_PLATFORM_BUILD_DIR = {
    "win32": "windows",
    "linux": "linux",
    "darwin": "mac",
}


# Default generator per platform (used when --generator auto)
_PLATFORM_DEFAULT_GENERATOR: dict[str, str] = {
    "win32": "Visual Studio 17 2022",
    "linux": "Ninja Multi-Config",
    "darwin": "Xcode",
}

# Generator name aliases for the CLI
_GENERATOR_ALIASES: dict[str, str] = {
    "vs": "Visual Studio 17 2022",
    "ninja": "Ninja Multi-Config",
    "xcode": "Xcode",
    "makefiles": "Unix Makefiles",
}


def _select_generator(choice: str | None) -> str | None:
    """Resolve the ``--generator`` option to a CMake generator string.

    Returns ``None`` when the platform default should be used (no ``-G``
    flag emitted) or an explicit generator string.

    ``auto`` picks the platform default.
    """
    if choice is None or choice == "auto":
        return _PLATFORM_DEFAULT_GENERATOR.get(sys.platform)
    alias = _GENERATOR_ALIASES.get(choice.lower())
    if alias:
        return alias
    # Pass through verbatim (user typed a full CMake generator name)
    return choice


_CMAKE_PRESETS_TEMPLATE = {
    "version": 4,
    "cmakeMinimumRequired": {"major": 3, "minor": 23, "patch": 0},
    "include": [],
}


def _ensure_project_cmake_presets(
    project_path: Path,
    engine_path: Path,
) -> bool:
    """Ensure the project's CMakePresets.json includes the engine's presets.

    If the file doesn't exist, creates it from a template.
    If it exists but doesn't include the engine, adds the include.
    Returns True if the file was created or modified.
    """
    preset_path = project_path / "CMakePresets.json"
    engine_presets = engine_path / "CMakePresets.json"

    if not engine_presets.exists():
        return False

    engine_include = engine_presets.as_posix()

    if preset_path.exists():
        try:
            data = json.loads(preset_path.read_text())
        except (json.JSONDecodeError, OSError):
            data = {}
    else:
        data = {}

    if not data:
        data = dict(_CMAKE_PRESETS_TEMPLATE)
        data["include"] = [engine_include]
        preset_path.write_text(json.dumps(data, indent=4) + "\n")
        return True

    includes = data.get("include", [])
    # Check if engine is already included (compare as posix paths)
    for inc in includes:
        if Path(inc).as_posix() == engine_include:
            return False

    # Replace includes to point at current engine only
    data["include"] = [engine_include]
    preset_path.write_text(json.dumps(data, indent=4) + "\n")
    return True


def _run_cmake(
    cmd: list[str],
    *,
    cwd: Path,
    on_line: "Callable[[str], None] | None" = None,
) -> int:
    """Run a CMake command with line-by-line output streaming.

    Uses ``subprocess.Popen`` so that each output line is emitted
    immediately (for GUI progress callbacks) and ``KeyboardInterrupt``
    (Ctrl+C) cleanly terminates the process tree.

    Parameters
    ----------
    cmd:
        The command list to execute.
    cwd:
        Working directory for the subprocess.
    on_line:
        Optional callback invoked for every stdout/stderr line.
        If *None*, lines are printed to stdout.

    Returns
    -------
    int
        The process return code.  ``-15`` (SIGTERM) on cancel.
    """
    import signal

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            stripped = line.rstrip("\n\r")
            if on_line is not None:
                on_line(stripped)
            else:
                print(stripped, flush=True)
        return proc.wait()
    except KeyboardInterrupt:
        # Graceful cancel — try SIGTERM first, then kill
        try:
            if sys.platform == "win32":
                # Windows: taskkill /T kills entire process tree
                subprocess.run(
                    ["taskkill", "/pid", str(proc.pid), "/f", "/t"],
                    capture_output=True,
                )
            else:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            proc.kill()
        console.print("\n[yellow]Build cancelled.[/yellow]")
        return -15


@workspace.command("build")
@click.argument("name_or_path")
@click.option(
    "--config", "-c",
    type=click.Choice(["debug", "profile", "release"]),
    default="profile",
    help="Build configuration (default: profile)",
)
@click.option(
    "--target", "-t",
    multiple=True,
    help="CMake build targets (e.g. Editor, MyProject.GameLauncher). "
         "If omitted, builds all default targets.",
)
@click.option(
    "--engine-centric",
    is_flag=True,
    help="Use engine-centric build mode (-S engine -DLY_PROJECTS=project)",
)
@click.option(
    "--configure-only",
    is_flag=True,
    help="Run CMake configure but skip the build step",
)
@click.option(
    "--reconfigure",
    is_flag=True,
    help="Force CMake reconfigure even if build directory exists",
)
@click.option(
    "--preset",
    default=None,
    help="CMake configure preset name (e.g. windows-default)",
)
@click.option(
    "--third-party-path",
    type=click.Path(exists=True),
    default=None,
    help="Override LY_3RDPARTY_PATH",
)
@click.option(
    "--parallel", "-j",
    type=int,
    default=None,
    help="Number of parallel build jobs",
)
@click.option(
    "--generator", "-G",
    default=None,
    help="CMake generator (auto, vs, ninja, xcode, makefiles, or full name). "
         "Default: auto-detect per platform.",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without executing",
)
def build_command(
    name_or_path: str,
    config: str,
    target: tuple[str, ...],
    engine_centric: bool,
    configure_only: bool,
    reconfigure: bool,
    preset: str | None,
    third_party_path: str | None,
    parallel: int | None,
    generator: str | None,
    as_json: bool,
    dry_run: bool,
) -> None:
    """Build an O3DE workspace using CMake.

    Reads workspace metadata to locate engine, project, and gems,
    then runs CMake configure + build.

    Project-centric mode (default):
        cmake -S <project> -B <project>/build/<platform> -DLY_3RDPARTY_PATH=...

    Engine-centric mode (--engine-centric):
        cmake -S <engine> -B <build_dir> -DLY_PROJECTS=<project> -DLY_3RDPARTY_PATH=...

    Examples:
        o3de workspace build my-workspace
        o3de workspace build ./workspace --config debug --target Editor
        o3de workspace build my-workspace --engine-centric --preset windows-default
    """

    from o3de_pilot.core.json_output import emit_response, emit_error

    # Find workspace
    ws_path = Path(name_or_path)
    if not ws_path.exists():
        ws_path = get_default_workspaces_path() / name_or_path

    if not ws_path.exists():
        if as_json:
            emit_error(f"Workspace not found: {name_or_path}", code="E_WS_NOT_FOUND")
        else:
            console.print(f"[red]Workspace not found:[/red] {name_or_path}")
        raise SystemExit(1)

    meta = _read_workspace_meta(ws_path)
    if meta is None:
        if as_json:
            emit_error(f"Not a valid workspace: {ws_path}", code="E_WS_INVALID")
        else:
            console.print(f"[red]Not a valid workspace:[/red] {ws_path}")
        raise SystemExit(1)

    # Resolve paths
    engine_path = _find_engine_path(meta)
    project_path = _find_project_path(meta)

    if not engine_path:
        if as_json:
            emit_error("No engine found in workspace metadata.", code="E_NO_ENGINE")
        else:
            console.print("[red]No engine found in workspace metadata.[/red]")
            console.print("[dim]Hint: Re-create the workspace with a registered engine.[/dim]")
        raise SystemExit(1)

    if not project_path and not engine_centric:
        engine_centric = True
        if not as_json:
            console.print(
                "[yellow]No project found in workspace — "
                "switching to engine-centric build.[/yellow]"
            )

    # Resolve third-party path (K6 resolution chain)
    tp_path: Path | None = None
    if third_party_path:
        tp_path = Path(third_party_path)
    else:
        tp_path = _find_third_party_path(meta=meta, engine_path=engine_path)

    # K5: Resolve generator
    cmake_generator = _select_generator(generator)

    # Platform build subdirectory
    platform_dir = _PLATFORM_BUILD_DIR.get(sys.platform, sys.platform)

    # Determine source and build directories
    if engine_centric:
        source_dir = engine_path
        build_dir = engine_path / "build" / platform_dir
    else:
        assert project_path is not None
        source_dir = project_path
        build_dir = project_path / "build" / platform_dir

    mode = "engine-centric" if engine_centric else "project-centric"

    if not as_json:
        console.print(f"[bold]Building workspace:[/bold] {meta.workspace.name}")
        console.print(f"  Mode: {mode}")
        console.print(f"  Config: {config}")
        console.print(f"  Source: {source_dir}")
        console.print(f"  Build dir: {build_dir}")
        if cmake_generator:
            console.print(f"  Generator: {cmake_generator}")
        if tp_path:
            console.print(f"  3rd-party: {tp_path}")

    # ------------------------------------------------------------------
    # K2: Ensure project CMakePresets.json includes engine presets
    # ------------------------------------------------------------------
    if not engine_centric and project_path:
        if _ensure_project_cmake_presets(project_path, engine_path):
            if not as_json:
                console.print(
                    "[dim]Updated project CMakePresets.json with engine include[/dim]"
                )

    # ------------------------------------------------------------------
    # Build configure + build commands
    # ------------------------------------------------------------------
    needs_configure = reconfigure or not (build_dir / "CMakeCache.txt").exists()
    configure_cmd: list[str] | None = None
    build_cmd_list: list[str] | None = None

    if needs_configure:
        if preset:
            configure_cmd = [
                "cmake",
                "--preset", preset,
                "-S", str(source_dir),
            ]
        else:
            configure_cmd = [
                "cmake",
                "-B", str(build_dir),
                "-S", str(source_dir),
            ]
            if cmake_generator:
                configure_cmd.append(f"-G{cmake_generator}")

        if tp_path:
            configure_cmd.append(f"-DLY_3RDPARTY_PATH={tp_path}")
        if engine_centric and project_path:
            configure_cmd.append(f"-DLY_PROJECTS={project_path}")

    if not configure_only:
        cmake_config = {"debug": "Debug", "profile": "Profile", "release": "Release"}[config]
        build_cmd_list = [
            "cmake",
            "--build", str(build_dir),
            "--config", cmake_config,
        ]
        if target:
            build_cmd_list.append("--target")
            build_cmd_list.extend(target)
        if parallel:
            build_cmd_list.extend(["--parallel", str(parallel)])
        else:
            build_cmd_list.append("--parallel")

    # ------------------------------------------------------------------
    # Dry-run: show commands and exit
    # ------------------------------------------------------------------
    if dry_run:
        commands = []
        if configure_cmd:
            commands.append(configure_cmd)
        if build_cmd_list:
            commands.append(build_cmd_list)

        if as_json:
            emit_response(data={
                "workspace": meta.workspace.name,
                "mode": mode,
                "config": config,
                "source_dir": str(source_dir),
                "build_dir": str(build_dir),
                "generator": cmake_generator,
                "third_party_path": str(tp_path) if tp_path else None,
                "commands": [" ".join(c) for c in commands],
                "dry_run": True,
            })
        else:
            console.print("\n[bold yellow]Dry run — commands that would be executed:[/bold yellow]")
            for cmd in commands:
                console.print(f"  [dim]$ {' '.join(cmd)}[/dim]")
        return

    # ------------------------------------------------------------------
    # Execute: CMake configure
    # ------------------------------------------------------------------
    if configure_cmd:
        if not as_json:
            console.print("\n[bold]Configuring...[/bold]")
            console.print(f"[dim]$ {' '.join(configure_cmd)}[/dim]")

        rc = _run_cmake(configure_cmd, cwd=source_dir)
        if rc != 0:
            if as_json:
                emit_error("CMake configure failed.", code="E_CONFIGURE_FAILED")
            else:
                console.print("[red]CMake configure failed.[/red]")
            raise SystemExit(rc)

        if not as_json:
            console.print("[green]Configure complete.[/green]")

    if configure_only:
        if as_json:
            emit_response(data={
                "workspace": meta.workspace.name,
                "phase": "configure",
                "status": "complete",
            })
        return

    # ------------------------------------------------------------------
    # Execute: CMake build
    # ------------------------------------------------------------------
    assert build_cmd_list is not None
    if not as_json:
        console.print("\n[bold]Building...[/bold]")
        console.print(f"[dim]$ {' '.join(build_cmd_list)}[/dim]")

    rc = _run_cmake(build_cmd_list, cwd=source_dir)
    if rc != 0:
        if as_json:
            emit_error("Build failed.", code="E_BUILD_FAILED")
        else:
            console.print("[red]Build failed.[/red]")
        raise SystemExit(rc)

    cmake_config = {"debug": "Debug", "profile": "Profile", "release": "Release"}[config]
    if as_json:
        emit_response(data={
            "workspace": meta.workspace.name,
            "mode": mode,
            "config": cmake_config,
            "source_dir": str(source_dir),
            "build_dir": str(build_dir),
        })
    else:
        console.print(f"\n[green]Build complete:[/green] {cmake_config}")


@workspace.command("lock")
@click.argument("name_or_path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def lock_command(name_or_path: str, as_json: bool) -> None:
    """Generate a lockfile for a workspace's resolved dependencies.

    Creates workspace-lock.json in the workspace directory, recording
    the exact versions of all resolved dependencies. Use with
    `workspace create --frozen` to reproduce exact builds.

    Example:
        o3de-pilot workspace lock my-workspace
    """
    from o3de_pilot.core.lockfile import generate_lockfile, read_lockfile
    from o3de_pilot.core.json_output import emit_response, emit_error

    ws_path = _resolve_workspace_path(name_or_path)
    if not ws_path or not ws_path.exists():
        if as_json:
            emit_error(f"Workspace not found: {name_or_path}", code="E_NOT_FOUND")
        else:
            console.print(f"[red]Workspace not found: {name_or_path}[/red]")
        raise SystemExit(1)

    # Read workspace metadata
    meta_path = ws_path / "workspace.json"
    if not meta_path.exists():
        if as_json:
            emit_error("No workspace.json found", code="E_NOT_FOUND")
        else:
            console.print("[red]No workspace.json found in workspace[/red]")
        raise SystemExit(1)

    with open(meta_path) as f:
        meta = json.load(f)

    # Extract resolved candidates from workspace metadata
    candidates = meta.get("resolved_candidates", meta.get("sources", {}))
    root_name = meta.get("root", meta.get("name", name_or_path))
    root_version = meta.get("rootVersion", meta.get("version", "0.0.0"))

    lockfile_path = generate_lockfile(
        workspace_path=ws_path,
        resolved_candidates=candidates,
        root_name=root_name,
        root_version=root_version,
    )

    if as_json:
        lockdata = read_lockfile(ws_path)
        emit_response(data={
            "lockfile": str(lockfile_path),
            "packages": len(lockdata.get("packages", {})),
            "contentHash": lockdata.get("contentHash", ""),
        })
    else:
        console.print(f"[green]Lockfile written:[/green] {lockfile_path}")


@workspace.command("verify-lock")
@click.argument("name_or_path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def verify_lock_command(name_or_path: str, as_json: bool) -> None:
    """Verify the workspace's current state matches its lockfile.

    Checks that the resolved dependencies match what's recorded
    in workspace-lock.json.
    """
    from o3de_pilot.core.lockfile import verify_lockfile
    from o3de_pilot.core.json_output import emit_error

    ws_path = _resolve_workspace_path(name_or_path)
    if not ws_path or not ws_path.exists():
        if as_json:
            emit_error(f"Workspace not found: {name_or_path}", code="E_NOT_FOUND")
        else:
            console.print(f"[red]Workspace not found: {name_or_path}[/red]")
        raise SystemExit(1)

    meta_path = ws_path / "workspace.json"
    if not meta_path.exists():
        if as_json:
            emit_error("No workspace.json found", code="E_NOT_FOUND")
        else:
            console.print("[red]No workspace.json found[/red]")
        raise SystemExit(1)

    with open(meta_path) as f:
        meta = json.load(f)

    candidates = meta.get("resolved_candidates", meta.get("sources", {}))
    matches, mismatches = verify_lockfile(ws_path, candidates)

    if as_json:
        console.print_json(json.dumps({
            "verified": matches,
            "mismatches": mismatches,
        }))
    else:
        if matches:
            console.print("[green]Lockfile verified — all packages match.[/green]")
        else:
            console.print("[red]Lockfile mismatch:[/red]")
            for m in mismatches:
                console.print(f"  • {m}")

    if not matches:
        raise SystemExit(1)


def _resolve_workspace_path(name_or_path: str) -> Path | None:
    """Resolve a workspace name or path to an actual directory."""
    p = Path(name_or_path)
    if p.is_dir():
        return p
    # Try under default workspaces directory
    ws_path = get_default_workspaces_path() / name_or_path
    if ws_path.is_dir():
        return ws_path
    return None
