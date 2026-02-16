# O3DE Pilot CLI - Repo Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Repo management commands."""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def repo() -> None:
    """Manage O3DE repos (object registries)."""
    pass


@repo.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_repos(as_json: bool) -> None:
    """List all registered repos."""
    from o3de_pilot.core.resolver import Resolver

    resolver = Resolver()
    resolver.resolve()
    repos = resolver.repos

    if as_json:
        import json as json_mod

        items = []
        for name, obj in repos.items():
            items.append(
                {"name": obj.name, "version": obj.version, "path": str(obj.path)}
            )
        click.echo(json_mod.dumps(items, indent=2))
        return

    if not repos:
        console.print("[yellow]No repos registered.[/yellow]")
        return

    table = Table(title="Registered Repos")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Path", style="dim")

    for name, obj in repos.items():
        table.add_row(obj.name, obj.version or "unknown", str(obj.path))

    console.print(table)


@repo.command("create")
@click.argument("name")
@click.option("--path", "-p", type=click.Path(), help="Repo path")
@click.option("--template", "-t", "template_name", help="Repo template to use")
def create_repo(name: str, path: str | None, template_name: str | None) -> None:
    """Create a new repo from a template.

    Scaffolds a minimal repo directory with a repo.2-0-0.json.
    If --template is given the template contents are applied first.
    """
    import json

    repo_path = Path(path) if path else Path.cwd() / name

    console.print(f"[bold]Creating repo:[/bold] {name}")

    if repo_path.exists():
        console.print(f"[red]Path already exists:[/red] {repo_path}")
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

    repo_path.mkdir(parents=True)

    if template_data and template_data.path.exists():
        import shutil

        for item in template_data.path.iterdir():
            if item.name.startswith("template"):
                continue
            dest = repo_path / item.name
            if item.is_dir():
                shutil.copytree(item, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(item, dest)
        console.print(f"[dim]Applied template: {template_name}[/dim]")

    repo_json = {
        "$schema": "https://overlo3de.com/o3de-repo-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "repo": {
            "name": name,
            "display_name": name.split(".")[-1],
            "version": "1.0.0",
            "description": f"A new O3DE repo: {name}",
        },
        "children": {},
    }
    with open(repo_path / "repo.2-0-0.json", "w") as f:
        json.dump(repo_json, f, indent=2)

    console.print(f"[green]Created repo:[/green] {repo_path}")
    console.print("[dim]Register it with: o3de-pilot repo register <path>[/dim]")


@repo.command("register")
@click.argument("path_or_url")
@click.option("--remote", is_flag=True, help="Register a remote URL instead of a local path")
def register_repo(path_or_url: str, remote: bool) -> None:
    """Register a repo by adding its path to the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path

    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    if remote:
        console.print(f"[bold]Registering remote repo:[/bold] {path_or_url}")
        section = manifest.setdefault("remote", {})
        repos_list = section.setdefault("repos", [])
        if path_or_url in repos_list:
            console.print("[yellow]Remote repo already registered.[/yellow]")
            return
        repos_list.append(path_or_url)
    else:
        repo_path = Path(path_or_url).resolve()
        console.print(f"[bold]Registering repo:[/bold] {repo_path}")
        is_repo = any(
            (repo_path / f).exists() for f in ["repo.2-0-0.json", "repo.json"]
        )
        if not is_repo:
            console.print("[red]No repo JSON found at this path.[/red]")
            raise SystemExit(1)
        section = manifest.setdefault("local", {})
        repos_list = section.setdefault("repos", [])
        path_str = repo_path.as_posix()
        if path_str in repos_list:
            console.print("[yellow]Repo already registered.[/yellow]")
            return
        repos_list.append(path_str)

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Registered repo:[/green] {path_or_url}")


@repo.command("unregister")
@click.argument("name")
@click.option("--remote", is_flag=True, help="Remove from remote section instead of local")
def unregister_repo(name: str, remote: bool) -> None:
    """Unregister a repo by removing it from the manifest."""
    import json
    from o3de_pilot.core.paths import get_manifest_path

    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    section_key = "remote" if remote else "local"
    label = "remote repo" if remote else "repo"
    console.print(f"[bold]Unregistering {label}:[/bold] {name}")

    section = manifest.get(section_key, {})
    repos_list = section.get("repos", [])

    original_len = len(repos_list)
    repos_list = [r for r in repos_list if name not in r]

    if len(repos_list) == original_len:
        console.print(f"[yellow]Repo '{name}' not found in {section_key} manifest.[/yellow]")
        return

    section["repos"] = repos_list
    manifest[section_key] = section

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    console.print(f"[green]Unregistered {label}:[/green] {name}")
