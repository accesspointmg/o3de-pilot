# O3DE Pilot CLI - Gem Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Gem management commands."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def gem() -> None:
    """Manage O3DE gems."""
    pass


@gem.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_gems(as_json: bool) -> None:
    """List all registered gems."""
    from o3de_pilot.core.manifest import get_manifest
    
    manifest = get_manifest()
    gems = manifest.get_gems()
    
    if as_json:
        import json
        click.echo(json.dumps([g.dict() for g in gems], indent=2))
        return
    
    if not gems:
        console.print("[yellow]No gems registered.[/yellow]")
        console.print("Use [bold]o3de-pilot install <gem>[/bold] to install gems.")
        return
    
    table = Table(title="Registered Gems")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Path", style="dim")
    
    for g in gems:
        table.add_row(g.name, g.version or "unknown", str(g.path))
    
    console.print(table)


@gem.command("create")
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Gem path")
@click.option("--template", "-t", "template_name", help="Gem template to use")
def create(name: str, path: str | None, template_name: str | None) -> None:
    """Create a new gem."""
    gem_path = Path(path) if path else Path.cwd() / name
    
    console.print(f"[bold]Creating gem:[/bold] {name}")
    console.print(f"[dim]Path: {gem_path}[/dim]")
    
    if template_name:
        console.print(f"[dim]Template: {template_name}[/dim]")
    
    # TODO: Implement gem creation
    console.print("[yellow]Gem creation not yet implemented.[/yellow]")


@gem.command("info")
@click.argument("name")
def info(name: str) -> None:
    """Show information about a gem."""
    console.print(f"[bold]Gem Info:[/bold] {name}")
    
    # TODO: Fetch gem info from registry or local
    console.print("[yellow]Gem info not yet implemented.[/yellow]")


@gem.command("search")
@click.argument("query")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(query: str, as_json: bool) -> None:
    """Search for gems in the registry."""
    console.print(f"[bold]Searching for gems:[/bold] {query}")
    
    # TODO: Search registry
    console.print("[yellow]Gem search not yet implemented.[/yellow]")
