# O3DE Pilot CLI - Deps Command
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Dependency tree visualization and management commands."""

import click
import json
from rich.console import Console
from rich.tree import Tree

from o3de_pilot.core import (
    Resolver,
    get_manifest_path,
)

console = Console()


@click.group()
def deps() -> None:
    """Dependency management and visualization."""
    pass


@deps.command("tree")
@click.argument("name", required=False)
@click.option("--depth", "-d", type=int, default=10, help="Max tree depth")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--all", "show_all", is_flag=True, help="Show all objects, not just one subtree")
def tree_command(name: str | None, depth: int, as_json: bool, show_all: bool) -> None:
    """Visualize the dependency graph as a tree.

    If NAME is given, shows the dependency tree rooted at that object.
    Otherwise shows the full dependency forest (all roots).

    Inspired by 'cargo tree'.
    """
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    resolver = Resolver(manifest_path)
    with console.status("Resolving manifest..."):
        resolver.resolve()

    if as_json:
        _output_json(resolver, name, depth, show_all)
        return

    if name:
        obj = resolver.objects.get(name)
        if not obj:
            # Try fuzzy match
            matches = [n for n in resolver.objects if name.lower() in n.lower()]
            if matches:
                console.print(f"[yellow]Object '{name}' not found. Did you mean:[/yellow]")
                for m in matches:
                    console.print(f"  {m}")
            else:
                console.print(f"[red]Object not found:[/red] {name}")
            raise SystemExit(1)

        tree = Tree(f"[bold cyan]{obj.name}[/bold cyan]@{obj.version} ({obj.object_type.value})")
        _build_tree(tree, obj, resolver, set(), depth, 0)
        console.print(tree)
    else:
        # Show full forest — find root objects (those with no parent and not only-deps)
        if show_all:
            roots = list(resolver.objects.values())
        else:
            roots = [obj for obj in resolver.objects.values() if obj.parent is None]

        if not roots:
            console.print("[dim]No objects resolved.[/dim]")
            return

        for root in roots:
            tree = Tree(f"[bold cyan]{root.name}[/bold cyan]@{root.version} ({root.object_type.value})")
            _build_tree(tree, root, resolver, set(), depth, 0)
            console.print(tree)
            console.print()


@deps.command("list")
@click.argument("name")
@click.option("--transitive", "-t", is_flag=True, help="Include transitive dependencies")
@click.option("--reverse", "-r", is_flag=True, help="Show reverse dependencies (who depends on this)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_deps(name: str, transitive: bool, reverse: bool, as_json: bool) -> None:
    """List dependencies for an object."""
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    resolver = Resolver(manifest_path)
    with console.status("Resolving manifest..."):
        resolver.resolve()

    obj = resolver.objects.get(name)
    if not obj:
        if as_json:
            from o3de_pilot.core.json_output import emit_error
            emit_error(f"Object not found: {name}", code="E_NOT_FOUND")
            return
        console.print(f"[red]Object not found:[/red] {name}")
        raise SystemExit(1)

    if reverse:
        # Find all objects that depend on this one
        dependents = []
        for other_name, other_obj in resolver.objects.items():
            for dep_spec in other_obj.dependencies:
                if dep_spec.name == name:
                    dependents.append((other_name, str(dep_spec)))
        if as_json:
            from o3de_pilot.core.json_output import emit_response
            emit_response(data={"object": name, "reverse_deps": [
                {"name": n, "constraint": c} for n, c in dependents
            ]})
            return
        if dependents:
            console.print(f"[bold]Objects depending on {name}:[/bold]")
            for dep_name, constraint in dependents:
                console.print(f"  {dep_name} (requires {constraint})")
        else:
            console.print(f"[dim]No objects depend on {name}.[/dim]")
        return

    # Direct dependencies
    console.print(f"[bold]Dependencies for {name}:[/bold]")
    if obj.dependencies:
        for dep_spec in obj.dependencies:
            candidate = resolver.objects.get(dep_spec.name)
            if candidate:
                status = "[green]resolved[/green]"
                version_info = f"@{candidate.version}"
            else:
                status = "[red]missing[/red]"
                version_info = ""
            console.print(f"  {dep_spec.name}{version_info} ({dep_spec.specifier or '*'}) {status}")
    else:
        console.print("  [dim]none[/dim]")

    if obj.optional_dependencies:
        console.print(f"\n[bold]Optional dependencies:[/bold]")
        for dep_spec in obj.optional_dependencies:
            candidate = resolver.objects.get(dep_spec.name)
            if candidate:
                console.print(f"  {dep_spec.name}@{candidate.version} [green]available[/green]")
            else:
                console.print(f"  {dep_spec.name} [dim]not installed[/dim]")

    if obj.peer_dependencies:
        console.print(f"\n[bold]Peer dependencies:[/bold]")
        for dep_spec in obj.peer_dependencies:
            candidate = resolver.objects.get(dep_spec.name)
            if candidate:
                console.print(f"  {dep_spec.name}@{candidate.version} [green]ok[/green]")
            else:
                console.print(f"  {dep_spec.name} [yellow]missing[/yellow]")

    if transitive:
        console.print(f"\n[bold]Transitive dependencies:[/bold]")
        locked = resolver.locked_dependencies.get(name, {})
        if locked:
            for dep_name, dep_version in locked.items():
                console.print(f"  {dep_name}@{dep_version}")
        else:
            console.print("  [dim]none[/dim]")

    if as_json:
        from o3de_pilot.core.json_output import emit_response
        deps_data = []
        for dep_spec in obj.dependencies:
            candidate = resolver.objects.get(dep_spec.name)
            deps_data.append({
                "name": dep_spec.name,
                "specifier": str(dep_spec.specifier or "*"),
                "resolved_version": candidate.version if candidate else None,
                "status": "resolved" if candidate else "missing",
            })
        data = {"object": name, "dependencies": deps_data}
        if transitive:
            data["transitive"] = resolver.locked_dependencies.get(name, {})
        emit_response(data=data)
        return


@deps.command("why")
@click.argument("name")
@click.argument("dependency")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def why_command(name: str, dependency: str, as_json: bool) -> None:
    """Explain why an object depends on another.

    Shows the dependency chain from NAME to DEPENDENCY.
    """
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        if as_json:
            from o3de_pilot.core.json_output import emit_error
            emit_error("No manifest found", code="E_NO_MANIFEST")
            return
        console.print("[red]No manifest found.[/red]")
        raise SystemExit(1)

    resolver = Resolver(manifest_path)
    with console.status("Resolving manifest..."):
        resolver.resolve()

    obj = resolver.objects.get(name)
    if not obj:
        if as_json:
            from o3de_pilot.core.json_output import emit_error
            emit_error(f"Object not found: {name}", code="E_NOT_FOUND")
            return
        console.print(f"[red]Object not found:[/red] {name}")
        raise SystemExit(1)

    # BFS to find path from name to dependency
    path = _find_dep_path(resolver, name, dependency)
    if as_json:
        from o3de_pilot.core.json_output import emit_response
        emit_response(data={"from": name, "to": dependency, "chain": path or []})
        return
    if path:
        console.print(f"[bold]Dependency chain:[/bold]")
        chain = " -> ".join(path)
        console.print(f"  {chain}")
    else:
        console.print(f"[dim]{name} does not depend on {dependency}[/dim]")


def _build_tree(
    parent_node: Tree,
    obj,
    resolver: Resolver,
    visited: set,
    max_depth: int,
    current_depth: int,
) -> None:
    """Recursively build a rich Tree from dependencies."""
    if current_depth >= max_depth:
        if obj.dependencies or obj.children:
            parent_node.add("[dim]...[/dim]")
        return

    # Add direct dependencies
    for dep_spec in obj.dependencies:
        if dep_spec.name in visited:
            parent_node.add(f"[dim]{dep_spec.name} (circular)[/dim]")
            continue

        candidate = resolver.objects.get(dep_spec.name)
        if candidate:
            visited.add(dep_spec.name)
            dep_label = f"[green]{candidate.name}[/green]@{candidate.version}"
            dep_node = parent_node.add(dep_label)
            _build_tree(dep_node, candidate, resolver, visited, max_depth, current_depth + 1)
        else:
            parent_node.add(f"[red]{dep_spec.name}[/red] (missing)")

    # Add optional deps with different styling
    for dep_spec in obj.optional_dependencies:
        candidate = resolver.objects.get(dep_spec.name)
        if candidate:
            parent_node.add(f"[dim]{candidate.name}@{candidate.version} (optional)[/dim]")
        else:
            parent_node.add(f"[dim]{dep_spec.name} (optional, not installed)[/dim]")

    # Add peer deps with warning styling
    for dep_spec in obj.peer_dependencies:
        candidate = resolver.objects.get(dep_spec.name)
        if candidate:
            parent_node.add(f"[blue]{candidate.name}@{candidate.version} (peer)[/blue]")
        else:
            parent_node.add(f"[yellow]{dep_spec.name} (peer, missing!)[/yellow]")

    # Add children
    for child in obj.children:
        if child.name in visited:
            parent_node.add(f"[dim]{child.name} (already shown)[/dim]")
            continue
        visited.add(child.name)
        child_label = f"[cyan]{child.name}[/cyan]@{child.version} ({child.object_type.value})"
        child_node = parent_node.add(child_label)
        _build_tree(child_node, child, resolver, visited, max_depth, current_depth + 1)


def _find_dep_path(resolver: Resolver, start: str, target: str) -> list[str] | None:
    """BFS to find shortest dependency path from start to target."""
    from collections import deque

    queue: deque[list[str]] = deque([[start]])
    visited: set[str] = {start}

    while queue:
        path = queue.popleft()
        current_name = path[-1]
        current_obj = resolver.objects.get(current_name)
        if not current_obj:
            continue

        for dep_spec in current_obj.dependencies:
            if dep_spec.name == target:
                return path + [target]
            if dep_spec.name not in visited and dep_spec.name in resolver.objects:
                visited.add(dep_spec.name)
                queue.append(path + [dep_spec.name])

    return None


def _output_json(resolver: Resolver, name: str | None, depth: int, show_all: bool) -> None:
    """Output dependency tree as JSON."""
    def _obj_to_dict(obj, visited: set, current_depth: int) -> dict:
        result = {
            "name": obj.name,
            "version": obj.version,
            "type": obj.object_type.value,
        }
        if current_depth < depth:
            deps = []
            for dep_spec in obj.dependencies:
                if dep_spec.name in visited:
                    deps.append({"name": dep_spec.name, "circular": True})
                    continue
                candidate = resolver.objects.get(dep_spec.name)
                if candidate:
                    visited.add(dep_spec.name)
                    deps.append(_obj_to_dict(candidate, visited, current_depth + 1))
                else:
                    deps.append({"name": dep_spec.name, "missing": True})
            if deps:
                result["dependencies"] = deps

            children = []
            for child in obj.children:
                if child.name not in visited:
                    visited.add(child.name)
                    children.append(_obj_to_dict(child, visited, current_depth + 1))
            if children:
                result["children"] = children

        return result

    if name:
        obj = resolver.objects.get(name)
        if obj:
            console.print_json(json.dumps(_obj_to_dict(obj, {name}, 0)))
        else:
            console.print_json(json.dumps({"error": f"Object not found: {name}"}))
    else:
        if show_all:
            roots = list(resolver.objects.values())
        else:
            roots = [obj for obj in resolver.objects.values() if obj.parent is None]
        forest = [_obj_to_dict(r, {r.name}, 0) for r in roots]
        console.print_json(json.dumps(forest))
