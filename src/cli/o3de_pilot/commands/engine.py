# O3DE Pilot CLI - Engine Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Engine management commands."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def engine() -> None:
    """Manage O3DE engines."""
    pass


@engine.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_engines(as_json: bool) -> None:
    """List all registered engines."""
    from o3de_pilot.core.manifest import get_manifest
    
    manifest = get_manifest()
    engines = manifest.get_engines()
    
    if as_json:
        import json
        click.echo(json.dumps([e.dict() for e in engines], indent=2))
        return
    
    if not engines:
        console.print("[yellow]No engines registered.[/yellow]")
        return
    
    table = Table(title="Registered Engines")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Path", style="dim")
    
    for e in engines:
        table.add_row(e.name, e.version or "unknown", str(e.path))
    
    console.print(table)


@engine.command("register")
@click.argument("path", type=click.Path(exists=True))
def register(path: str) -> None:
    """Register an O3DE engine."""
    engine_path = Path(path)
    
    console.print(f"[bold]Registering engine:[/bold] {engine_path}")
    
    # TODO: Implement engine registration
    console.print("[yellow]Engine registration not yet implemented.[/yellow]")


@engine.command("unregister")
@click.argument("name")
def unregister(name: str) -> None:
    """Unregister an O3DE engine."""
    console.print(f"[bold]Unregistering engine:[/bold] {name}")
    
    # TODO: Implement engine unregistration
    console.print("[yellow]Engine unregistration not yet implemented.[/yellow]")
