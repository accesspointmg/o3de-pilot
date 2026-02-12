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
    from o3de_pilot.core.resolver import Resolver
    
    resolver = Resolver()
    resolver.resolve()
    engines = resolver.engines
    
    if as_json:
        import json
        items = []
        for name, obj in engines.items():
            items.append({"name": obj.name, "version": obj.version, "path": str(obj.path)})
        click.echo(json.dumps(items, indent=2))
        return
    
    if not engines:
        console.print("[yellow]No engines registered.[/yellow]")
        return
    
    table = Table(title="Registered Engines")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Path", style="dim")
    
    for name, obj in engines.items():
        table.add_row(obj.name, obj.version or "unknown", str(obj.path))
    
    console.print(table)


@engine.command("register")
@click.argument("path", type=click.Path(exists=True))
def register(path: str) -> None:
    """Register an O3DE engine by adding it to the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path
    
    engine_path = Path(path).resolve()
    
    console.print(f"[bold]Registering engine:[/bold] {engine_path}")
    
    # Verify it's an engine (has engine.json or engine.2-0-0.json)
    is_engine = any((engine_path / f).exists() for f in ["engine.2-0-0.json", "engine.json"])
    if not is_engine:
        console.print("[red]No engine JSON found at this path.[/red]")
        raise SystemExit(1)
    
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Add to local.engines (Schema 2.0.0) or engines (legacy)
    local = manifest.setdefault("local", {})
    engines_list = local.setdefault("engines", [])
    
    path_str = engine_path.as_posix()
    if path_str in engines_list:
        console.print("[yellow]Engine already registered.[/yellow]")
        return
    
    engines_list.append(path_str)
    
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    console.print(f"[green]Registered engine:[/green] {engine_path}")


@engine.command("unregister")
@click.argument("name")
def unregister(name: str) -> None:
    """Unregister an O3DE engine by removing it from the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path
    
    console.print(f"[bold]Unregistering engine:[/bold] {name}")
    
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    local = manifest.get("local", {})
    engines_list = local.get("engines", [])
    
    # Find and remove by name match
    original_len = len(engines_list)
    engines_list = [e for e in engines_list if name not in e]
    
    if len(engines_list) == original_len:
        console.print(f"[yellow]Engine '{name}' not found in manifest.[/yellow]")
        return
    
    local["engines"] = engines_list
    manifest["local"] = local
    
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    console.print(f"[green]Unregistered engine:[/green] {name}")
