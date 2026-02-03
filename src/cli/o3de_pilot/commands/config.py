# O3DE Pilot CLI - Config Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Configuration management commands."""

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def config() -> None:
    """Manage O3DE Pilot configuration."""
    pass


@config.command("get")
@click.argument("key", required=False)
def get(key: str | None) -> None:
    """Get configuration value(s)."""
    from o3de_pilot.core.config import get_config
    
    cfg = get_config()
    
    if key:
        value = cfg.get(key)
        if value is not None:
            console.print(f"{key} = {value}")
        else:
            console.print(f"[yellow]Key not found:[/yellow] {key}")
    else:
        # Show all config
        table = Table(title="Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        
        for k, v in cfg.all().items():
            table.add_row(k, str(v))
        
        console.print(table)


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str) -> None:
    """Set a configuration value."""
    from o3de_pilot.core.config import get_config
    
    cfg = get_config()
    cfg.set(key, value)
    cfg.save()
    
    console.print(f"[green]Set:[/green] {key} = {value}")


@config.command("unset")
@click.argument("key")
def unset(key: str) -> None:
    """Remove a configuration value."""
    from o3de_pilot.core.config import get_config
    
    cfg = get_config()
    cfg.unset(key)
    cfg.save()
    
    console.print(f"[green]Unset:[/green] {key}")


@config.command("list")
def list_config() -> None:
    """List all configuration values."""
    from o3de_pilot.core.config import get_config
    
    cfg = get_config()
    
    table = Table(title="Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    
    for k, v in cfg.all().items():
        # Mask sensitive values
        display_value = "********" if "key" in k.lower() or "secret" in k.lower() else str(v)
        table.add_row(k, display_value)
    
    console.print(table)


@config.command("path")
def show_path() -> None:
    """Show configuration file path."""
    from o3de_pilot.core.config import get_config_path
    
    console.print(f"[bold]Config file:[/bold] {get_config_path()}")
