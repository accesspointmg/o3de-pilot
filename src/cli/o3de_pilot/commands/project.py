# O3DE Pilot CLI - Project Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Project management commands."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def project() -> None:
    """Manage O3DE projects."""
    pass


@project.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_projects(as_json: bool) -> None:
    """List all registered projects."""
    from o3de_pilot.core.manifest import get_manifest
    
    manifest = get_manifest()
    projects = manifest.get_projects()
    
    if as_json:
        import json
        click.echo(json.dumps([p.dict() for p in projects], indent=2))
        return
    
    if not projects:
        console.print("[yellow]No projects registered.[/yellow]")
        console.print("Use [bold]o3de-pilot init <name>[/bold] to create a new project.")
        return
    
    table = Table(title="Registered Projects")
    table.add_column("Name", style="cyan")
    table.add_column("Path", style="dim")
    table.add_column("Engine", style="green")
    
    for proj in projects:
        table.add_row(proj.name, str(proj.path), proj.engine_name or "default")
    
    console.print(table)


@project.command("init")
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Project path")
@click.option("--template", "-t", "template_name", help="Template to use")
def init_command(name: str, path: str | None, template_name: str | None) -> None:
    """Create a new O3DE project."""
    init_project(name, path, template_name)


def init_project(name: str, path: str | None, template_name: str | None) -> None:
    """Initialize a new O3DE project."""
    project_path = Path(path) if path else Path.cwd() / name
    
    console.print(f"[bold]Creating project:[/bold] {name}")
    console.print(f"[dim]Path: {project_path}[/dim]")
    
    if template_name:
        console.print(f"[dim]Template: {template_name}[/dim]")
    
    # TODO: Implement project creation via core module
    console.print("[yellow]Project creation not yet implemented.[/yellow]")


@project.command("build")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
@click.option("--config", "-c", type=click.Choice(["debug", "profile", "release"]), default="profile")
def build(path: str | None, config: str) -> None:
    """Build an O3DE project."""
    project_path = Path(path) if path else Path.cwd()
    
    console.print(f"[bold]Building project:[/bold] {project_path.name}")
    console.print(f"[dim]Configuration: {config}[/dim]")
    
    # TODO: Implement build via cmake
    console.print("[yellow]Build not yet implemented.[/yellow]")


@project.command("run")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
def run(path: str | None) -> None:
    """Run an O3DE project."""
    project_path = Path(path) if path else Path.cwd()
    
    console.print(f"[bold]Running project:[/bold] {project_path.name}")
    
    # TODO: Implement project launch
    console.print("[yellow]Run not yet implemented.[/yellow]")


@project.command("add")
@click.argument("obj_type", type=click.Choice(["gem"]))
@click.argument("name")
@click.option("--path", "-p", type=click.Path(exists=True), help="Project path")
def add(obj_type: str, name: str, path: str | None) -> None:
    """Add a gem to the project."""
    project_path = Path(path) if path else Path.cwd()
    
    console.print(f"[bold]Adding {obj_type}:[/bold] {name}")
    console.print(f"[dim]To project: {project_path}[/dim]")
    
    # TODO: Implement gem addition
    console.print("[yellow]Add not yet implemented.[/yellow]")
