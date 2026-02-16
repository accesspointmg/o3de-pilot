# O3DE Pilot CLI - Overlay Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Overlay management commands."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def overlay() -> None:
    """Manage O3DE overlays (override layers)."""
    pass


@overlay.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_overlays(as_json: bool) -> None:
    """List all registered overlays."""
    from o3de_pilot.core.resolver import Resolver

    resolver = Resolver()
    resolver.resolve()
    overlays = resolver.overlays

    if as_json:
        import json as json_mod

        items = []
        for name, obj in overlays.items():
            items.append(
                {"name": obj.name, "version": obj.version, "path": str(obj.path)}
            )
        click.echo(json_mod.dumps(items, indent=2))
        return

    if not overlays:
        console.print("[yellow]No overlays registered.[/yellow]")
        return

    table = Table(title="Registered Overlays")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Path", style="dim")

    for name, obj in overlays.items():
        table.add_row(obj.name, obj.version or "unknown", str(obj.path))

    console.print(table)


@overlay.command("create")
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Overlay path")
@click.option("--template", "-t", "template_name", help="Overlay template to use")
def create_overlay(name: str, path: str | None, template_name: str | None) -> None:
    """Create a new overlay from a template.

    Scaffolds a minimal overlay directory with an overlay.2-0-0.json.
    If --template is given the template contents are applied first.
    """
    import json

    overlay_path = Path(path) if path else Path.cwd() / name

    console.print(f"[bold]Creating overlay:[/bold] {name}")

    if overlay_path.exists():
        console.print(f"[red]Path already exists:[/red] {overlay_path}")
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

    overlay_path.mkdir(parents=True)

    if template_data and template_data.path.exists():
        import shutil

        for item in template_data.path.iterdir():
            if item.name.startswith("template"):
                continue
            dest = overlay_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        console.print(f"[dim]Applied template: {template_name}[/dim]")

    overlay_json = {
        "$schema": "https://overlo3de.com/o3de-overlay-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "overlay": {
            "name": name,
            "display_name": name.split(".")[-1],
            "version": "1.0.0",
            "description": f"A new O3DE overlay: {name}",
        },
    }
    with open(overlay_path / "overlay.2-0-0.json", "w") as f:
        json.dump(overlay_json, f, indent=2)

    console.print(f"[green]Created overlay:[/green] {overlay_path}")
    console.print("[dim]Register it with: o3de-pilot overlay register <path>[/dim]")


@overlay.command("register")
@click.argument("path_or_url")
@click.option("--remote", is_flag=True, help="Register a remote URL instead of a local path")
def register_overlay(path_or_url: str, remote: bool) -> None:
    """Register an overlay by adding its path to the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path

    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    if remote:
        console.print(f"[bold]Registering remote overlay:[/bold] {path_or_url}")
        section = manifest.setdefault("remote", {})
        overlays_list = section.setdefault("overlays", [])
        if path_or_url in overlays_list:
            console.print("[yellow]Remote overlay already registered.[/yellow]")
            return
        overlays_list.append(path_or_url)
    else:
        overlay_path = Path(path_or_url).resolve()
        console.print(f"[bold]Registering overlay:[/bold] {overlay_path}")
        is_overlay = any(
            (overlay_path / f).exists()
            for f in ["overlay.2-0-0.json", "overlay.json"]
        )
        if not is_overlay:
            console.print("[red]No overlay JSON found at this path.[/red]")
            raise SystemExit(1)
        section = manifest.setdefault("local", {})
        overlays_list = section.setdefault("overlays", [])
        path_str = overlay_path.as_posix()
        if path_str in overlays_list:
            console.print("[yellow]Overlay already registered.[/yellow]")
            return
        overlays_list.append(path_str)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Registered overlay:[/green] {path_or_url}")


@overlay.command("unregister")
@click.argument("name")
@click.option("--remote", is_flag=True, help="Remove from remote section instead of local")
def unregister_overlay(name: str, remote: bool) -> None:
    """Unregister an overlay by removing it from the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path

    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    section_key = "remote" if remote else "local"
    label = "remote overlay" if remote else "overlay"
    console.print(f"[bold]Unregistering {label}:[/bold] {name}")

    section = manifest.get(section_key, {})
    overlays_list = section.get("overlays", [])

    original_len = len(overlays_list)
    overlays_list = [o for o in overlays_list if name not in o]

    if len(overlays_list) == original_len:
        console.print(f"[yellow]Overlay '{name}' not found in {section_key} manifest.[/yellow]")
        return

    section["overlays"] = overlays_list
    manifest[section_key] = section

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Unregistered {label}:[/green] {name}")
