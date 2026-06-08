# O3DE Pilot CLI - Registry Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Package registry commands."""

import click
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from o3de_pilot.core import (
    Store, 
    ObjectType,
    get_manifest_path,
    get_resolved_manifest_path,
    Resolver,
)
from o3de_pilot.core.models import get_object_name, get_object_version

console = Console()


@click.group()
def registry() -> None:
    """Manage package registry."""
    pass


@registry.command("search")
@click.argument("query")
@click.option("--type", "-t", "obj_type", type=click.Choice(["gem", "template", "project", "engine", "all"]), default="all")
@click.option("--remote", "-r", is_flag=True, help="Search remote repos only")
@click.option("--local", "-l", is_flag=True, help="Search local objects only")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search_command(query: str, obj_type: str, remote: bool, local: bool, as_json: bool) -> None:
    """Search the registry for packages."""
    search_registry(query, obj_type, remote, local, as_json)


def search_registry(query: str, obj_type: str, remote: bool = False, local: bool = False, as_json: bool = False) -> None:
    """Search the registry for packages."""
    # Map type string to ObjectType
    type_filter = None
    if obj_type != "all":
        type_filter = ObjectType(obj_type)
    
    results = []
    
    if not remote:
        # Search local resolved manifest
        resolved_path = get_resolved_manifest_path()
        if resolved_path.exists():
            with open(resolved_path) as f:
                resolved = json.load(f)
            
            for name, obj_data in resolved.get("objects", {}).items():
                # Filter by type
                if type_filter and obj_data.get("type") != type_filter.value:
                    continue
                
                # Match query
                if query.lower() in name.lower():
                    results.append({
                        "name": name,
                        "version": obj_data.get("version", ""),
                        "type": obj_data.get("type", ""),
                        "path": obj_data.get("path", ""),
                        "source": "local",
                    })
    
    if not local:
        # Search remote store
        store = Store()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("Searching remotes...", total=None)
            
            # Search cached remote objects
            remote_results = store.search(query, object_type=type_filter)
            
            for obj in remote_results:
                results.append({
                    "name": obj.name,
                    "version": obj.version,
                    "type": obj.object_type.value if obj.object_type else "",
                    "url": obj.url,
                    "source": "remote",
                })
    
    if as_json:
        console.print_json(json.dumps(results))
    else:
        if not results:
            console.print(f"[yellow]No results for:[/yellow] {query}")
            return
        
        table = Table(title=f"Search: {query}")
        table.add_column("Name", style="cyan")
        table.add_column("Version", style="green")
        table.add_column("Type", style="blue")
        table.add_column("Source", style="dim")
        
        for r in results:
            table.add_row(r["name"], r["version"], r["type"], r["source"])
        
        console.print(table)


@registry.command("install")
@click.argument("package")
@click.option("--version", "-v", "version", help="Specific version to install")
@click.option("--path", "-p", type=click.Path(), help="Install path")
@click.option("--dry-run", is_flag=True, help="Show what would be installed without downloading")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def install_command(package: str, version: str | None, path: str | None, dry_run: bool, as_json: bool) -> None:
    """Install a package from the registry."""
    install_package(package, version, path, dry_run=dry_run, as_json=as_json)


def install_package(package: str, version: str | None, install_path: str | None = None, dry_run: bool = False, as_json: bool = False) -> None:
    """Install a package from the registry."""
    from pathlib import Path
    from o3de_pilot.core.paths import get_default_path_for_type
    from o3de_pilot.core.models import ObjectType
    
    version_str = f"@{version}" if version else ""
    if not as_json:
        console.print(f"[bold]Installing:[/bold] {package}{version_str}")
    
    store = Store()
    
    # Search for the package - first try cached/refreshed store
    results = store.search(package)
    
    if not results:
        if as_json:
            from o3de_pilot.core.json_output import emit_error
            emit_error(f"Package not found: {package}", code="E_NOT_FOUND")
            return
        console.print(f"[red]Package not found:[/red] {package}")
        console.print("[dim]Try 'registry refresh' to update the package index.[/dim]")
        return
    
    # Find exact match or best match
    obj = None
    for r in results:
        if r.name == package:
            if version is None or r.version == version:
                obj = r
                break
    
    if not obj:
        obj = results[0]  # Take first result
    
    # Determine install path based on object type
    if install_path:
        target_path = Path(install_path)
    else:
        target_path = get_default_path_for_type(obj.object_type)
    
    if dry_run:
        data = {
            "dry_run": True,
            "package": obj.name,
            "version": obj.version,
            "type": obj.object_type.value,
            "target": str(target_path),
        }
        if obj.source_control_url:
            data["source"] = obj.source_control_url
        elif obj.download_url:
            data["download"] = obj.download_url
        if as_json:
            from o3de_pilot.core.json_output import emit_response
            emit_response(data=data)
            return
        console.print(f"[yellow]Dry-run:[/yellow] Would install {obj.name}@{obj.version}")
        console.print(f"  Type: {obj.object_type.value}")
        console.print(f"  Target: {target_path}")
        if obj.source_control_url:
            console.print(f"  Source: {obj.source_control_url}")
        elif obj.download_url:
            console.print(f"  Download: {obj.download_url}")
        return
    
    console.print(f"[dim]Installing to: {target_path}[/dim]")
    
    # Download
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Downloading {obj.name}...", total=None)
        
        try:
            download_path = store.download_sync(
                obj, target_path, expected_sha256=obj.source_sha256
            )
            progress.update(task, description="Done")
            if as_json:
                from o3de_pilot.core.json_output import emit_response
                emit_response(data={"package": obj.name, "version": obj.version, "path": str(download_path)})
                return
            console.print(f"[green]Installed:[/green] {download_path}")
            
            # Add to manifest
            console.print("[dim]Adding to manifest...[/dim]")
            from o3de_pilot.commands.manifest import add_command
            ctx = click.Context(add_command)
            ctx.invoke(add_command, path=str(download_path))
            
        except Exception as e:
            if as_json:
                from o3de_pilot.core.json_output import emit_error
                emit_error(str(e), code="E_INSTALL_FAILED")
                return
            console.print(f"[red]Installation failed:[/red] {e}")


@registry.command("uninstall")
@click.argument("package")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def uninstall(package: str, as_json: bool) -> None:
    """Uninstall a package."""
    import json
    from o3de_pilot.core.paths import get_manifest_path
    
    if not as_json:
        console.print(f"[bold]Uninstalling:[/bold] {package}")
    
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        if as_json:
            from o3de_pilot.core.json_output import emit_error
            emit_error("No manifest found", code="E_NO_MANIFEST")
            return
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    # Search local paths for the package name
    local = manifest.get("local", {})
    removed = False
    
    for obj_type in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
        paths = local.get(obj_type, [])
        original_len = len(paths)
        paths = [p for p in paths if package not in p]
        if len(paths) < original_len:
            local[obj_type] = paths
            removed = True
    
    if not removed:
        if as_json:
            from o3de_pilot.core.json_output import emit_error
            emit_error(f"Package '{package}' not found in manifest", code="E_NOT_FOUND")
            return
        console.print(f"[yellow]Package '{package}' not found in manifest.[/yellow]")
        return
    
    manifest["local"] = local
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    if as_json:
        from o3de_pilot.core.json_output import emit_response
        emit_response(data={"package": package, "uninstalled": True})
        return
    console.print(f"[green]Removed {package} from manifest.[/green]")
    console.print("[dim]Run 'manifest resolve' to update resolved manifest.[/dim]")


@registry.command("update")
@click.argument("package", required=False)
def update(package: str | None) -> None:
    """Update package(s) to latest version by re-resolving from remotes."""
    from o3de_pilot.core.store import Store
    from rich.progress import Progress, SpinnerColumn, TextColumn
    
    store = Store()
    
    if package:
        console.print(f"[bold]Updating:[/bold] {package}")
        results = store.search(package)
        if not results:
            console.print(f"[yellow]Package not found:[/yellow] {package}")
            return
        
        obj = results[0]
        console.print(f"  Latest: {obj.name}@{obj.version}")
        console.print("[dim]Re-install with: registry install {package}[/dim]")
    else:
        console.print("[bold]Refreshing all remotes...[/bold]")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Refreshing...", total=None)
            store.refresh_sync()
            progress.update(task, description="Done")
        
        console.print("[green]Remote index updated.[/green]")
        console.print("[dim]Run 'manifest resolve' to detect available updates.[/dim]")


@registry.command("list")
@click.argument("obj_type", type=click.Choice(["projects", "gems", "templates", "engines"]))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_command(obj_type: str, as_json: bool) -> None:
    """List registered objects."""
    list_objects(obj_type, as_json)


def list_objects(obj_type: str, as_json: bool) -> None:
    """List registered objects of a given type."""
    # Delegate to appropriate command
    if obj_type == "projects":
        from o3de_pilot.commands.project import list_projects
        # We need to invoke the click command properly
        ctx = click.Context(list_projects)
        ctx.invoke(list_projects, as_json=as_json)
    elif obj_type == "gems":
        from o3de_pilot.commands.gem import list_gems
        ctx = click.Context(list_gems)
        ctx.invoke(list_gems, as_json=as_json)
    elif obj_type == "templates":
        from o3de_pilot.commands.template import list_templates
        ctx = click.Context(list_templates)
        ctx.invoke(list_templates, as_json=as_json)
    elif obj_type == "engines":
        from o3de_pilot.commands.engine import list_engines
        ctx = click.Context(list_engines)
        ctx.invoke(list_engines, as_json=as_json)


@registry.command("refresh")
@click.option("--force", "-f", is_flag=True, help="Force refresh even if cache is fresh")
def refresh_command(force: bool) -> None:
    """Refresh the remote package index.
    
    Downloads metadata from all configured remote repos.
    """
    manifest_path = get_manifest_path()
    
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        console.print("Run 'o3de-pilot init' to set up.")
        raise SystemExit(1)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    remotes = manifest.get("remotes", [])
    
    if not remotes:
        console.print("[yellow]No remote repos configured.[/yellow]")
        console.print("Add remotes with 'o3de-pilot registry add-remote <url>'")
        return
    
    store = Store()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        total = len(remotes)
        task = progress.add_task("Refreshing...", total=total)
        
        for i, remote_url in enumerate(remotes):
            progress.update(task, description=f"Fetching {remote_url}...", completed=i)
            try:
                store.refresh_sync([remote_url])
            except Exception as e:
                console.print(f"[yellow]Warning:[/yellow] Failed to refresh {remote_url}: {e}")
        
        progress.update(task, description="Done", completed=total)
    
    console.print(f"[green]Refreshed {len(remotes)} remote(s)[/green]")


@registry.command("add-remote")
@click.argument("url")
@click.option("--name", "-n", help="Friendly name for the remote")
def add_remote_command(url: str, name: str | None) -> None:
    """Add a remote repository.
    
    Example:
        o3de-pilot registry add-remote https://canonical.o3de.org/repo.json
    """
    manifest_path = get_manifest_path()
    
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)
    else:
        manifest = {
            "$schema": "https://canonical.o3de.org/o3de-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "local": {},
            "remotes": [],
            "default": {},
        }
    
    remotes = manifest.setdefault("remotes", [])
    
    if url in remotes:
        console.print(f"[yellow]Already configured:[/yellow] {url}")
        return
    
    remotes.append(url)
    
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    console.print(f"[green]Added remote:[/green] {url}")
    console.print("Run 'o3de-pilot registry refresh' to fetch packages.")


@registry.command("remove-remote")
@click.argument("url")
def remove_remote_command(url: str) -> None:
    """Remove a remote repository."""
    manifest_path = get_manifest_path()
    
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    remotes = manifest.get("remotes", [])
    
    if url not in remotes:
        console.print(f"[yellow]Not found:[/yellow] {url}")
        return
    
    remotes.remove(url)
    
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    
    console.print(f"[green]Removed:[/green] {url}")


@registry.command("list-remotes")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_remotes_command(as_json: bool) -> None:
    """List configured remote repositories."""
    manifest_path = get_manifest_path()
    
    if not manifest_path.exists():
        if as_json:
            console.print_json("[]")
        else:
            console.print("[dim]No manifest found.[/dim]")
        return
    
    with open(manifest_path) as f:
        manifest = json.load(f)
    
    remotes = manifest.get("remotes", [])
    
    if as_json:
        console.print_json(json.dumps(remotes))
    else:
        if not remotes:
            console.print("[dim]No remotes configured.[/dim]")
            return
        
        console.print("[bold]Remote repositories:[/bold]")
        for remote in remotes:
            console.print(f"  • {remote}")


@registry.command("login")
@click.argument("registry_url")
@click.option("--token", "-t", help="Auth token (prompted if not provided)")
def login_command(registry_url: str, token: str | None) -> None:
    """Store an authentication token for a private registry.

    Token is saved in ~/.o3de/credentials.json (owner-readable only).
    """
    from o3de_pilot.core.auth import set_token

    if not token:
        token = click.prompt("Token", hide_input=True)

    set_token(registry_url, token)
    console.print(f"[green]Token saved for {registry_url}[/green]")


@registry.command("logout")
@click.argument("registry_url")
def logout_command(registry_url: str) -> None:
    """Remove a stored authentication token for a registry."""
    from o3de_pilot.core.auth import remove_token

    if remove_token(registry_url):
        console.print(f"[green]Token removed for {registry_url}[/green]")
    else:
        console.print(f"[yellow]No token found for {registry_url}[/yellow]")


@registry.command("whoami")
@click.argument("registry_url")
def whoami_command(registry_url: str) -> None:
    """Check if a token is stored for a registry."""
    from o3de_pilot.core.auth import get_token

    token = get_token(registry_url)
    if token:
        # Show masked token
        masked = token[:4] + "..." + token[-4:] if len(token) > 8 else "****"
        console.print(f"[green]Authenticated:[/green] {registry_url} (token: {masked})")
    else:
        console.print(f"[yellow]Not authenticated:[/yellow] {registry_url}")
