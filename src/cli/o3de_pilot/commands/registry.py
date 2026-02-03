# O3DE Pilot CLI - Registry Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Package registry commands."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def registry() -> None:
    """Manage package registry."""
    pass


@registry.command("search")
@click.argument("query")
@click.option("--type", "-t", "obj_type", type=click.Choice(["gem", "template", "project", "all"]), default="all")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search_command(query: str, obj_type: str, as_json: bool) -> None:
    """Search the registry for packages."""
    search_registry(query, obj_type, as_json)


def search_registry(query: str, obj_type: str, as_json: bool) -> None:
    """Search the registry for packages."""
    console.print(f"[bold]Searching registry:[/bold] {query}")
    
    if obj_type != "all":
        console.print(f"[dim]Type filter: {obj_type}[/dim]")
    
    # TODO: Implement registry search
    console.print("[yellow]Registry search not yet implemented.[/yellow]")


@registry.command("install")
@click.argument("package")
@click.option("--version", "-v", "version", help="Specific version to install")
def install_command(package: str, version: str | None) -> None:
    """Install a package from the registry."""
    install_package(package, version)


def install_package(package: str, version: str | None) -> None:
    """Install a package from the registry."""
    version_str = f"@{version}" if version else ""
    console.print(f"[bold]Installing:[/bold] {package}{version_str}")
    
    # TODO: Implement package installation
    console.print("[yellow]Package installation not yet implemented.[/yellow]")


@registry.command("uninstall")
@click.argument("package")
def uninstall(package: str) -> None:
    """Uninstall a package."""
    console.print(f"[bold]Uninstalling:[/bold] {package}")
    
    # TODO: Implement package uninstallation
    console.print("[yellow]Package uninstallation not yet implemented.[/yellow]")


@registry.command("update")
@click.argument("package", required=False)
def update(package: str | None) -> None:
    """Update package(s) to latest version."""
    if package:
        console.print(f"[bold]Updating:[/bold] {package}")
    else:
        console.print("[bold]Updating all packages...[/bold]")
    
    # TODO: Implement package update
    console.print("[yellow]Package update not yet implemented.[/yellow]")


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
