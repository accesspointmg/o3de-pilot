# O3DE Pilot CLI - Entry Point
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Main entry point for o3de-pilot CLI."""

import click
from rich.console import Console

from o3de_pilot import __version__
from o3de_pilot.commands import project, gem, template, engine, registry, ai, config

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="o3de-pilot")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """O3DE Pilot - AI-powered O3DE project management.

    A modern CLI for managing O3DE projects, gems, templates, and engines
    with npm-style package management and AI assistance.
    """
    ctx.ensure_object(dict)


# Register command groups
cli.add_command(project.project)
cli.add_command(gem.gem)
cli.add_command(template.template)
cli.add_command(engine.engine)
cli.add_command(registry.registry)
cli.add_command(ai.ai)
cli.add_command(config.config)


# Convenience aliases at top level
@cli.command()
@click.argument("query")
@click.option("--type", "-t", "obj_type", type=click.Choice(["gem", "template", "project", "all"]), default="all")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def search(query: str, obj_type: str, as_json: bool) -> None:
    """Search the registry for packages."""
    from o3de_pilot.commands.registry import search_registry
    search_registry(query, obj_type, as_json)


@cli.command()
@click.argument("package")
@click.option("--version", "-v", "version", help="Specific version to install")
def install(package: str, version: str | None) -> None:
    """Install a gem, template, or other package."""
    from o3de_pilot.commands.registry import install_package
    install_package(package, version)


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
