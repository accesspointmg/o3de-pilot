# O3DE Pilot CLI - Template Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Template management commands."""

import click
from pathlib import Path
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


@template.command("create")
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Template path")
@click.option("--source", "-s", type=click.Path(exists=True),
              help="Source directory to create template from")
def create_template(name: str, path: str | None, source: str | None) -> None:
    """Create a new template from a source directory.

    If --source is given, the source directory's contents are copied into
    the new template.  Otherwise a minimal skeleton is created.
    """
    import json
    import shutil

    tpl_path = Path(path) if path else Path.cwd() / name

    console.print(f"[bold]Creating template:[/bold] {name}")

    if tpl_path.exists():
        console.print(f"[red]Path already exists:[/red] {tpl_path}")
        raise SystemExit(1)

    tpl_path.mkdir(parents=True)

    # Copy source contents if provided
    if source:
        src = Path(source)
        for item in src.iterdir():
            dest = tpl_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        console.print(f"[dim]Copied source: {src}[/dim]")
    else:
        # Minimal skeleton
        (tpl_path / "Template").mkdir()

    # Create template.2-0-0.json
    tpl_json = {
        "$schema": "https://overlo3de.com/o3de-template-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "template": {
            "name": name,
            "display_name": name.split(".")[-1],
            "version": "1.0.0",
            "description": f"A new O3DE template: {name}",
        },
    }
    with open(tpl_path / "template.2-0-0.json", "w") as f:
        json.dump(tpl_json, f, indent=2)

    console.print(f"[green]Created template:[/green] {tpl_path}")
    console.print("[dim]Register it with: o3de-pilot template register <path>[/dim]")


@template.command("instance")
@click.argument("template_name")
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Instance output path")
def instance_template(template_name: str, name: str, path: str | None) -> None:
    """Instantiate a template to create a new object.

    Copies the template contents to a new directory, replacing
    placeholder tokens with the instance NAME.
    """
    import shutil

    inst_path = Path(path) if path else Path.cwd() / name

    console.print(f"[bold]Instantiating template:[/bold] {template_name} -> {name}")

    if inst_path.exists():
        console.print(f"[red]Path already exists:[/red] {inst_path}")
        raise SystemExit(1)

    # Locate the template
    from o3de_pilot.core.resolver import Resolver

    resolver = Resolver()
    resolver.resolve()

    tpl_obj = None
    for tpl_name, tpl in resolver.templates.items():
        if template_name in tpl_name or template_name == tpl_name:
            tpl_obj = tpl
            break

    if not tpl_obj or not tpl_obj.path.exists():
        console.print(f"[red]Template not found:[/red] {template_name}")
        raise SystemExit(1)

    # Copy template contents
    inst_path.mkdir(parents=True)
    for item in tpl_obj.path.iterdir():
        if item.name.startswith("template"):
            continue  # Skip template metadata
        dest = inst_path / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    console.print(f"[green]Created instance:[/green] {inst_path}")
    console.print("[dim]Register it with: o3de-pilot register add <path>[/dim]")


@template.command("register")
@click.argument("path_or_url")
@click.option("--remote", is_flag=True, help="Register a remote URL instead of a local path")
def register_template(path_or_url: str, remote: bool) -> None:
    """Register a template by adding its path to the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path

    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    if remote:
        console.print(f"[bold]Registering remote template:[/bold] {path_or_url}")
        section = manifest.setdefault("remote", {})
        templates_list = section.setdefault("templates", [])
        if path_or_url in templates_list:
            console.print("[yellow]Remote template already registered.[/yellow]")
            return
        templates_list.append(path_or_url)
    else:
        tpl_path = Path(path_or_url).resolve()
        console.print(f"[bold]Registering template:[/bold] {tpl_path}")
        is_tpl = any(
            (tpl_path / f).exists()
            for f in ["template.2-0-0.json", "template.json"]
        )
        if not is_tpl:
            console.print("[red]No template JSON found at this path.[/red]")
            raise SystemExit(1)
        section = manifest.setdefault("local", {})
        templates_list = section.setdefault("templates", [])
        path_str = tpl_path.as_posix()
        if path_str in templates_list:
            console.print("[yellow]Template already registered.[/yellow]")
            return
        templates_list.append(path_str)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Registered template:[/green] {path_or_url}")


@template.command("unregister")
@click.argument("name")
@click.option("--remote", is_flag=True, help="Remove from remote section instead of local")
def unregister_template(name: str, remote: bool) -> None:
    """Unregister a template by removing it from the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path

    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    section_key = "remote" if remote else "local"
    label = "remote template" if remote else "template"
    console.print(f"[bold]Unregistering {label}:[/bold] {name}")

    section = manifest.get(section_key, {})
    templates_list = section.get("templates", [])

    original_len = len(templates_list)
    templates_list = [t for t in templates_list if name not in t]

    if len(templates_list) == original_len:
        console.print(f"[yellow]Template '{name}' not found in {section_key} manifest.[/yellow]")
        return

    section["templates"] = templates_list
    manifest[section_key] = section

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Unregistered {label}:[/green] {name}")
