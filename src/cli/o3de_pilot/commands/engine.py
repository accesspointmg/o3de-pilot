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


@engine.command("create")
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Engine path")
@click.option("--template", "-t", "template_name", help="Engine template to use")
def create_engine(name: str, path: str | None, template_name: str | None) -> None:
    """Create a new engine from a template.

    Scaffolds a minimal engine directory with an engine.2-0-0.json.
    If --template is given the template contents are applied first.
    """
    import json

    engine_path = Path(path) if path else Path.cwd() / name

    console.print(f"[bold]Creating engine:[/bold] {name}")

    if engine_path.exists():
        console.print(f"[red]Path already exists:[/red] {engine_path}")
        raise SystemExit(1)

    template_data = None
    if template_name:
        try:
            from o3de_pilot.core.resolver import Resolver

            resolver = Resolver()
            resolver.resolve()
            for tpl_name, tpl_obj in resolver.templates.items():
                if template_name in tpl_name or template_name == tpl_name:
                    template_data = tpl_obj
                    break
        except Exception:
            pass

    engine_path.mkdir(parents=True)

    if template_data and template_data.path.exists():
        import shutil

        for item in template_data.path.iterdir():
            if item.name.startswith("template"):
                continue
            dest = engine_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        console.print(f"[dim]Applied template: {template_name}[/dim]")
    else:
        (engine_path / "Gems").mkdir()
        (engine_path / "Templates").mkdir()

    engine_json = {
        "$schema": "https://overlo3de.com/o3de-engine-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "engine": {
            "name": name,
            "display_name": name.split(".")[-1],
            "version": "1.0.0",
            "description": f"A new O3DE engine: {name}",
        },
    }
    with open(engine_path / "engine.2-0-0.json", "w") as f:
        json.dump(engine_json, f, indent=2)

    console.print(f"[green]Created engine:[/green] {engine_path}")
    console.print("[dim]Register it with: o3de-pilot engine register <path>[/dim]")


@engine.command("register")
@click.argument("path_or_url")
@click.option("--remote", is_flag=True, help="Register a remote URL instead of a local path")
def register(path_or_url: str, remote: bool) -> None:
    """Register an O3DE engine by adding it to the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path

    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    if remote:
        console.print(f"[bold]Registering remote engine:[/bold] {path_or_url}")
        section = manifest.setdefault("remote", {})
        engines_list = section.setdefault("engines", [])
        if path_or_url in engines_list:
            console.print("[yellow]Remote engine already registered.[/yellow]")
            return
        engines_list.append(path_or_url)
    else:
        engine_path = Path(path_or_url).resolve()
        console.print(f"[bold]Registering engine:[/bold] {engine_path}")
        is_engine = any((engine_path / f).exists() for f in ["engine.2-0-0.json", "engine.json"])
        if not is_engine:
            console.print("[red]No engine JSON found at this path.[/red]")
            raise SystemExit(1)
        section = manifest.setdefault("local", {})
        engines_list = section.setdefault("engines", [])
        path_str = engine_path.as_posix()
        if path_str in engines_list:
            console.print("[yellow]Engine already registered.[/yellow]")
            return
        engines_list.append(path_str)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Registered engine:[/green] {path_or_url}")


@engine.command("unregister")
@click.argument("name")
@click.option("--remote", is_flag=True, help="Remove from remote section instead of local")
def unregister(name: str, remote: bool) -> None:
    """Unregister an O3DE engine by removing it from the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path

    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    section_key = "remote" if remote else "local"
    label = "remote engine" if remote else "engine"
    console.print(f"[bold]Unregistering {label}:[/bold] {name}")

    section = manifest.get(section_key, {})
    engines_list = section.get("engines", [])

    original_len = len(engines_list)
    engines_list = [e for e in engines_list if name not in e]

    if len(engines_list) == original_len:
        console.print(f"[yellow]Engine '{name}' not found in {section_key} manifest.[/yellow]")
        return

    section["engines"] = engines_list
    manifest[section_key] = section

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Unregistered {label}:[/green] {name}")
