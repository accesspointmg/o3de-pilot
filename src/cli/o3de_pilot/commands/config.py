# O3DE Pilot CLI - Config Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Configuration management commands."""

import json
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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def get(key: str | None, as_json: bool) -> None:
    """Get configuration value(s)."""
    from o3de_pilot.core.config import get_config
    
    cfg = get_config()
    
    if key:
        value = cfg.get(key)
        if as_json:
            from o3de_pilot.core.json_output import emit_response, emit_error
            if value is not None:
                emit_response(data={"key": key, "value": value})
            else:
                emit_error(f"Key not found: {key}", code="E_KEY_NOT_FOUND")
            return
        if value is not None:
            console.print(f"{key} = {value}")
        else:
            console.print(f"[yellow]Key not found:[/yellow] {key}")
    else:
        if as_json:
            from o3de_pilot.core.json_output import emit_response
            emit_response(data=cfg.all())
            return
        table = Table(title="Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        
        for k, v in cfg.all().items():
            table.add_row(k, str(v))
        
        console.print(table)


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def set_config(key: str, value: str, as_json: bool) -> None:
    """Set a configuration value."""
    from o3de_pilot.core.config import get_config
    
    cfg = get_config()
    cfg.set(key, value)
    cfg.save()
    
    if as_json:
        from o3de_pilot.core.json_output import emit_response
        emit_response(data={"key": key, "value": value})
        return
    console.print(f"[green]Set:[/green] {key} = {value}")


@config.command("unset")
@click.argument("key")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def unset(key: str, as_json: bool) -> None:
    """Remove a configuration value."""
    from o3de_pilot.core.config import get_config
    
    cfg = get_config()
    cfg.unset(key)
    cfg.save()
    
    if as_json:
        from o3de_pilot.core.json_output import emit_response
        emit_response(data={"key": key})
        return
    console.print(f"[green]Unset:[/green] {key}")


@config.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_config(as_json: bool) -> None:
    """List all configuration values."""
    from o3de_pilot.core.config import get_config
    
    cfg = get_config()
    
    if as_json:
        from o3de_pilot.core.json_output import emit_response
        # Mask sensitive values even in JSON
        data = {}
        for k, v in cfg.all().items():
            if "key" in k.lower() or "secret" in k.lower():
                data[k] = "********"
            else:
                data[k] = v
        emit_response(data=data)
        return

    table = Table(title="Configuration")
    table.add_column("Key", style="cyan")
    table.add_column("Value", style="green")
    
    for k, v in cfg.all().items():
        display_value = "********" if "key" in k.lower() or "secret" in k.lower() else str(v)
        table.add_row(k, display_value)
    
    console.print(table)


@config.command("path")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_path(as_json: bool) -> None:
    """Show configuration file path."""
    from o3de_pilot.core.config import get_config_path
    
    if as_json:
        from o3de_pilot.core.json_output import emit_response
        emit_response(data={"path": str(get_config_path())})
        return
    console.print(f"[bold]Config file:[/bold] {get_config_path()}")
