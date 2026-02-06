# O3DE Pilot CLI - GUI Command
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Launch the O3DE Pilot graphical user interface.
"""

import click
from pathlib import Path


@click.command("gui")
@click.option(
    "--manifest",
    "-m",
    type=click.Path(exists=True, path_type=Path),
    help="Path to manifest file to load"
)
@click.option(
    "--demo",
    is_flag=True,
    help="Load demo objects for testing"
)
@click.pass_context
def gui(ctx, manifest: Path | None, demo: bool):
    """Launch the graphical user interface.
    
    Opens the O3DE Pilot GUI for browsing and managing objects
    (engines, projects, gems, templates, repos, overlays).
    
    Examples:
    
        # Launch GUI with default manifest
        o3de-pilot gui
        
        # Launch GUI with specific manifest
        o3de-pilot gui --manifest ~/.o3de/o3de_manifest.json
        
        # Launch GUI with demo objects
        o3de-pilot gui --demo
    """
    try:
        from ..gui.app import run_gui
    except ImportError as e:
        click.secho("Error: PySide6 is required for the GUI.", fg="red")
        click.secho("Install it with: pip install 'o3de-pilot[gui]'", fg="yellow")
        raise click.Abort() from e
    
    exit_code = run_gui(manifest_path=manifest, demo=demo)
    ctx.exit(exit_code)
