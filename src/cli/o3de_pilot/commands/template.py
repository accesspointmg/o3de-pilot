# O3DE Pilot CLI - Template Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Template management commands."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def template() -> None:
    """Manage O3DE templates."""
    pass


@template.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_templates(as_json: bool) -> None:
    """List all registered templates."""
    from o3de_pilot.core.manifest import get_manifest
    
    manifest = get_manifest()
    templates = manifest.get_templates()
    
    if as_json:
        import json
        click.echo(json.dumps([t.dict() for t in templates], indent=2))
        return
    
    if not templates:
        console.print("[yellow]No templates registered.[/yellow]")
        return
    
    table = Table(title="Registered Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Path", style="dim")
    
    for t in templates:
        table.add_row(t.name, t.template_type or "project", str(t.path))
    
    console.print(table)


@template.command("info")
@click.argument("name")
def info(name: str) -> None:
    """Show information about a template."""
    console.print(f"[bold]Template Info:[/bold] {name}")
    
    # TODO: Fetch template info
    console.print("[yellow]Template info not yet implemented.[/yellow]")
