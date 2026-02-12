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
    from o3de_pilot.core.resolver import Resolver
    
    resolver = Resolver()
    resolver.resolve()
    templates = resolver.templates
    
    if as_json:
        import json
        items = []
        for name, obj in templates.items():
            items.append({"name": obj.name, "version": obj.version, "path": str(obj.path)})
        click.echo(json.dumps(items, indent=2))
        return
    
    if not templates:
        console.print("[yellow]No templates registered.[/yellow]")
        return
    
    table = Table(title="Registered Templates")
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Path", style="dim")
    
    for name, obj in templates.items():
        tpl_type = obj.data.get("template_type") or "project"
        table.add_row(obj.name, tpl_type, str(obj.path))
    
    console.print(table)


@template.command("info")
@click.argument("name")
def info(name: str) -> None:
    """Show information about a template."""
    from o3de_pilot.core.resolver import load_resolved_manifest
    
    try:
        resolved = load_resolved_manifest()
    except Exception:
        console.print("[yellow]No resolved manifest. Run 'manifest resolve' first.[/yellow]")
        raise SystemExit(1)
    
    obj_data = None
    for obj_name, obj_info in resolved.get("objects", {}).items():
        if obj_info.get("type") == "template" and (name in obj_name or name == obj_name):
            obj_data = obj_info
            obj_data["_name"] = obj_name
            break
    
    if not obj_data:
        console.print(f"[red]Template not found:[/red] {name}")
        raise SystemExit(1)
    
    console.print(f"\n[bold cyan]{obj_data['_name']}[/bold cyan]")
    console.print(f"  Version:  {obj_data.get('version', 'unknown')}")
    console.print(f"  Path:     {obj_data.get('path', 'unknown')}")
    
    meta = obj_data.get("display_metadata") or {}
    if meta.get("display_name"):
        console.print(f"  Display:  {meta['display_name']}")
    if meta.get("summary"):
        console.print(f"  Summary:  {meta['summary']}")
    
    console.print()
