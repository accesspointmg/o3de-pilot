# O3DE Pilot CLI - Entry Point
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Main entry point for o3de-pilot CLI."""

import click
from rich.console import Console

from o3de_pilot import __version__
from o3de_pilot.commands import project, gem, template, engine, registry, ai, config
from o3de_pilot.commands import manifest as manifest_cmd
from o3de_pilot.commands import workspace as workspace_cmd
from o3de_pilot.commands import gui as gui_cmd
from o3de_pilot.commands import register as register_cmd
from o3de_pilot.commands import publish as publish_cmd
from o3de_pilot.commands import audit as audit_cmd
from o3de_pilot.commands import deps as deps_cmd
from o3de_pilot.commands import repo as repo_cmd
from o3de_pilot.commands import overlay as overlay_cmd

console = Console()


def ensure_first_run_setup() -> None:
    """Initialize user directories on first run."""
    from o3de_pilot.core import get_manifest_path, initialize_user_directories
    
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        # First run - initialize everything
        paths = initialize_user_directories()
        
        # Create default manifest
        from o3de_pilot.core.paths import get_default_manifest_data
        import json
        
        manifest_data = get_default_manifest_data()
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f, indent=2)


@click.group()
@click.version_option(version=__version__, prog_name="o3de-pilot")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """O3DE Pilot - AI-powered O3DE project management.

    A modern CLI for managing O3DE projects, gems, templates, and engines
    with npm-style package management and AI assistance.
    """
    ctx.ensure_object(dict)
    
    # Ensure first-run setup (except for help commands)
    if ctx.invoked_subcommand not in (None, "help"):
        ensure_first_run_setup()


# Register command groups
cli.add_command(project.project)
cli.add_command(gem.gem)
cli.add_command(template.template)
cli.add_command(engine.engine)
cli.add_command(registry.registry)
cli.add_command(manifest_cmd.manifest)
cli.add_command(workspace_cmd.workspace)
cli.add_command(ai.ai)
cli.add_command(config.config)
cli.add_command(gui_cmd.gui)
cli.add_command(register_cmd.register)
cli.add_command(register_cmd.unregister)
cli.add_command(publish_cmd.publish)
cli.add_command(audit_cmd.audit)
cli.add_command(deps_cmd.deps)
cli.add_command(repo_cmd.repo)
cli.add_command(overlay_cmd.overlay)


# MCP server command
@cli.command("mcp")
def mcp_command() -> None:
    """Start MCP (Model Context Protocol) server on stdio.
    
    Exposes o3de-pilot CLI commands as MCP tools for AI agents,
    VS Code Copilot, and other MCP-compliant clients.
    """
    from o3de_pilot.mcp_server import serve
    serve()


# Convenience aliases at top level
@cli.command()
@click.argument("query")
@click.option("--type", "-t", "obj_type", type=click.Choice(["gem", "template", "project", "engine", "all"]), default="all")
@click.option("--remote", "-r", is_flag=True, help="Search remote repos only")
@click.option("--local", "-l", is_flag=True, help="Search local objects only")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(query: str, obj_type: str, remote: bool, local: bool, as_json: bool) -> None:
    """Search the registry for packages."""
    from o3de_pilot.commands.registry import search_registry
    search_registry(query, obj_type, remote, local, as_json)


@cli.command()
@click.argument("package")
@click.option("--version", "-v", "version", help="Specific version to install")
@click.option("--path", "-p", type=click.Path(), help="Install path")
def install(package: str, version: str | None, path: str | None) -> None:
    """Install a gem, template, or other package."""
    from o3de_pilot.commands.registry import install_package
    install_package(package, version, path)


@cli.command()
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Project path")
@click.option("--template", "-t", "template_name", help="Template to use")
def init(name: str, path: str | None, template_name: str | None) -> None:
    """Initialize a new O3DE project."""
    from o3de_pilot.commands.project import init_project
    init_project(name, path, template_name)


@cli.command("list")
@click.argument("obj_type", type=click.Choice(["projects", "gems", "templates", "engines"]))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_objects(obj_type: str, as_json: bool) -> None:
    """List registered objects."""
    from o3de_pilot.commands.registry import list_objects
    list_objects(obj_type, as_json)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
