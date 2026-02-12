# O3DE Pilot CLI - Workspace Command
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Workspace commands for multi-project coordination."""

import click
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from o3de_pilot.core import (
    Resolver,
    get_manifest_path,
    get_resolved_manifest_path,
)
from o3de_pilot.core.models import get_object_name, get_object_version

console = Console()


@click.group()
def workspace() -> None:
    """Manage multi-project workspaces.

    A workspace coordinates multiple projects sharing the same
    engine and gem installations.
    """
    pass


@workspace.command("init")
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Workspace root directory")
def init_workspace(name: str, path: str | None) -> None:
    """Initialize a new workspace.

    Creates a workspace config file that tracks which projects,
    engine, and shared gems belong together.
    """
    workspace_dir = Path(path) if path else Path.cwd()
    workspace_dir.mkdir(parents=True, exist_ok=True)

    workspace_file = workspace_dir / "o3de-workspace.json"
    if workspace_file.exists():
        console.print(f"[yellow]Workspace already exists:[/yellow] {workspace_file}")
        return

    workspace_data = {
        "$schema": "https://overlo3de.com/o3de-workspace-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "name": name,
        "engine": None,
        "projects": [],
        "shared_gems": [],
    }

    with open(workspace_file, "w") as f:
        json.dump(workspace_data, f, indent=2)

    console.print(f"[green]Created workspace:[/green] {workspace_file}")
    console.print("[dim]Add projects with 'workspace add-project <path>'[/dim]")


@workspace.command("status")
@click.option("--path", "-p", type=click.Path(exists=True), help="Workspace root")
def status(path: str | None) -> None:
    """Show workspace status — engine, projects, shared gems."""
    workspace_dir = Path(path) if path else Path.cwd()
    workspace_file = workspace_dir / "o3de-workspace.json"

    if not workspace_file.exists():
        console.print("[red]No workspace found.[/red] Run 'workspace init <name>' first.")
        raise SystemExit(1)

    with open(workspace_file) as f:
        ws = json.load(f)

    console.print(Panel(f"[bold]{ws.get('name', 'Unnamed')}[/bold]", title="Workspace"))

    engine = ws.get("engine")
    if engine:
        console.print(f"  Engine: [cyan]{engine}[/cyan]")
    else:
        console.print("  Engine: [yellow]not set[/yellow]")

    projects = ws.get("projects", [])
    if projects:
        console.print(f"\n  Projects ({len(projects)}):")
        for proj in projects:
            p = Path(proj)
            exists = "[green]ok[/green]" if p.exists() else "[red]missing[/red]"
            console.print(f"    {exists} {proj}")
    else:
        console.print("\n  Projects: [dim]none[/dim]")

    gems = ws.get("shared_gems", [])
    if gems:
        console.print(f"\n  Shared Gems ({len(gems)}):")
        for gem in gems:
            p = Path(gem)
            exists = "[green]ok[/green]" if p.exists() else "[red]missing[/red]"
            console.print(f"    {exists} {gem}")


@workspace.command("add-project")
@click.argument("project_path", type=click.Path(exists=True))
@click.option("--workspace", "-w", "ws_path", type=click.Path(exists=True), help="Workspace root")
def add_project(project_path: str, ws_path: str | None) -> None:
    """Add a project to the workspace."""
    workspace_dir = Path(ws_path) if ws_path else Path.cwd()
    workspace_file = workspace_dir / "o3de-workspace.json"

    if not workspace_file.exists():
        console.print("[red]No workspace found.[/red]")
        raise SystemExit(1)

    resolved = Path(project_path).resolve().as_posix()

    with open(workspace_file) as f:
        ws = json.load(f)

    projects = ws.setdefault("projects", [])
    if resolved in projects:
        console.print(f"[yellow]Already in workspace:[/yellow] {resolved}")
        return

    projects.append(resolved)

    with open(workspace_file, "w") as f:
        json.dump(ws, f, indent=2)

    console.print(f"[green]Added project:[/green] {resolved}")


@workspace.command("remove-project")
@click.argument("project_path")
@click.option("--workspace", "-w", "ws_path", type=click.Path(exists=True), help="Workspace root")
def remove_project(project_path: str, ws_path: str | None) -> None:
    """Remove a project from the workspace."""
    workspace_dir = Path(ws_path) if ws_path else Path.cwd()
    workspace_file = workspace_dir / "o3de-workspace.json"

    if not workspace_file.exists():
        console.print("[red]No workspace found.[/red]")
        raise SystemExit(1)

    with open(workspace_file) as f:
        ws = json.load(f)

    projects = ws.get("projects", [])
    # Match by exact path or by name contained in path
    resolved = Path(project_path).resolve().as_posix()
    original_len = len(projects)
    projects = [p for p in projects if p != resolved and project_path not in p]

    if len(projects) == original_len:
        console.print(f"[yellow]Not found in workspace:[/yellow] {project_path}")
        return

    ws["projects"] = projects

    with open(workspace_file, "w") as f:
        json.dump(ws, f, indent=2)

    console.print(f"[green]Removed project:[/green] {project_path}")


@workspace.command("set-engine")
@click.argument("engine_path", type=click.Path(exists=True))
@click.option("--workspace", "-w", "ws_path", type=click.Path(exists=True), help="Workspace root")
def set_engine(engine_path: str, ws_path: str | None) -> None:
    """Set the engine for this workspace."""
    workspace_dir = Path(ws_path) if ws_path else Path.cwd()
    workspace_file = workspace_dir / "o3de-workspace.json"

    if not workspace_file.exists():
        console.print("[red]No workspace found.[/red]")
        raise SystemExit(1)

    resolved = Path(engine_path).resolve().as_posix()

    with open(workspace_file) as f:
        ws = json.load(f)

    ws["engine"] = resolved

    with open(workspace_file, "w") as f:
        json.dump(ws, f, indent=2)

    console.print(f"[green]Engine set to:[/green] {resolved}")


@workspace.command("add-gem")
@click.argument("gem_path", type=click.Path(exists=True))
@click.option("--workspace", "-w", "ws_path", type=click.Path(exists=True), help="Workspace root")
def add_gem(gem_path: str, ws_path: str | None) -> None:
    """Add a shared gem to the workspace."""
    workspace_dir = Path(ws_path) if ws_path else Path.cwd()
    workspace_file = workspace_dir / "o3de-workspace.json"

    if not workspace_file.exists():
        console.print("[red]No workspace found.[/red]")
        raise SystemExit(1)

    resolved = Path(gem_path).resolve().as_posix()

    with open(workspace_file) as f:
        ws = json.load(f)

    gems = ws.setdefault("shared_gems", [])
    if resolved in gems:
        console.print(f"[yellow]Already in workspace:[/yellow] {resolved}")
        return

    gems.append(resolved)

    with open(workspace_file, "w") as f:
        json.dump(ws, f, indent=2)

    console.print(f"[green]Added shared gem:[/green] {resolved}")
