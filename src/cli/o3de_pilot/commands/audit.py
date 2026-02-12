# O3DE Pilot CLI - Audit Command
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Dependency tree audit command."""

import click
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree

from o3de_pilot.core import (
    Resolver,
    get_manifest_path,
)
from o3de_pilot.core.store import compute_sha256

console = Console()


@click.command("audit")
@click.option("--fix", is_flag=True, help="Attempt to auto-fix issues")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
def audit(fix: bool, as_json: bool) -> None:
    """Audit the dependency tree for issues.

    Scans for:
    - Deprecated objects still in use
    - Missing integrity checksums on releases
    - Unresolved dependencies (missing or version mismatch)
    - Missing peer dependencies
    - Unresolvable optional dependencies
    - Version conflicts between siblings
    """
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        console.print("[red]No manifest found.[/red] Run 'o3de-pilot init' first.")
        raise SystemExit(1)

    resolver = Resolver(manifest_path)

    with console.status("Resolving manifest..."):
        resolver.resolve()

    issues = _collect_issues(resolver)

    if as_json:
        console.print_json(json.dumps({
            "total": sum(len(v) for v in issues.values()),
            "issues": issues,
        }))
    else:
        _display_issues(issues)

    total = sum(len(v) for v in issues.values())
    if total > 0:
        raise SystemExit(1)


def _collect_issues(resolver: Resolver) -> dict[str, list[dict]]:
    """Collect all audit issues from a resolved manifest.

    Returns a dict keyed by issue category.
    """
    issues: dict[str, list[dict]] = {
        "deprecated": [],
        "missing_integrity": [],
        "missing_dependencies": [],
        "missing_peer_dependencies": [],
        "unresolvable_optional": [],
        "conflicts": [],
    }

    for name, obj in resolver.objects.items():
        # --- Deprecated check ---
        type_key = obj.object_type.value
        type_data = obj.data.get(type_key, {})
        deprecated = type_data.get("deprecated") if isinstance(type_data, dict) else None
        if not deprecated:
            deprecated = obj.data.get("deprecated")
        if deprecated:
            msg = deprecated.get("message", str(deprecated)) if isinstance(deprecated, dict) else str(deprecated)
            replacement = deprecated.get("replacement", "") if isinstance(deprecated, dict) else ""
            issues["deprecated"].append({
                "object": name,
                "message": msg,
                "replacement": replacement,
            })

        # --- Missing integrity on releases ---
        releases = obj.data.get("releases", [])
        if isinstance(releases, list):
            for i, release in enumerate(releases):
                if not isinstance(release, dict):
                    continue
                rel_name = release.get("name", f"release[{i}]")
                for j, dl in enumerate(release.get("downloads", [])):
                    if not isinstance(dl, dict):
                        continue
                    if dl.get("source") and not dl.get("source_sha256"):
                        issues["missing_integrity"].append({
                            "object": name,
                            "release": rel_name,
                            "field": f"downloads[{j}].source_sha256",
                        })
                    if dl.get("lfs") and not dl.get("lfs_sha256"):
                        issues["missing_integrity"].append({
                            "object": name,
                            "release": rel_name,
                            "field": f"downloads[{j}].lfs_sha256",
                        })
                for j, binary in enumerate(release.get("binaries", [])):
                    if not isinstance(binary, dict):
                        continue
                    if binary.get("binary") and not binary.get("sha256"):
                        issues["missing_integrity"].append({
                            "object": name,
                            "release": rel_name,
                            "field": f"binaries[{j}].sha256",
                        })

        # --- Missing dependencies ---
        for dep_spec in obj.dependencies:
            candidate = resolver.objects.get(dep_spec.name)
            if candidate is None:
                issues["missing_dependencies"].append({
                    "object": name,
                    "dependency": str(dep_spec),
                    "reason": "not found",
                })
            elif not dep_spec.matches(candidate.version):
                issues["missing_dependencies"].append({
                    "object": name,
                    "dependency": str(dep_spec),
                    "reason": f"version mismatch (found {candidate.version})",
                })

        # --- Missing peer dependencies ---
        for peer_spec in obj.peer_dependencies:
            candidate = resolver.objects.get(peer_spec.name)
            if candidate is None:
                issues["missing_peer_dependencies"].append({
                    "object": name,
                    "peer": str(peer_spec),
                    "reason": "not installed",
                })
            elif not peer_spec.matches(candidate.version):
                issues["missing_peer_dependencies"].append({
                    "object": name,
                    "peer": str(peer_spec),
                    "reason": f"version mismatch (found {candidate.version})",
                })

        # --- Unresolvable optional dependencies ---
        for opt_spec in obj.optional_dependencies:
            candidate = resolver.objects.get(opt_spec.name)
            if candidate is not None and not opt_spec.matches(candidate.version):
                issues["unresolvable_optional"].append({
                    "object": name,
                    "optional": str(opt_spec),
                    "reason": f"found {candidate.version} but constraint not met",
                })

    # --- Version conflicts ---
    for conflict in resolver.conflicts:
        issues["conflicts"].append({
            "dependency": conflict.dependency_name,
            "requirer_a": conflict.requirer_a,
            "constraint_a": conflict.constraint_a,
            "requirer_b": conflict.requirer_b,
            "constraint_b": conflict.constraint_b,
            "resolved_version": conflict.resolved_version,
        })

    # Remove empty categories
    return {k: v for k, v in issues.items() if v}


def _display_issues(issues: dict[str, list[dict]]) -> None:
    """Display audit issues in a rich table."""
    total = sum(len(v) for v in issues.values())

    if not issues:
        console.print("[green]No issues found — dependency tree is healthy.[/green]")
        return

    console.print(f"\n[bold red]Found {total} issue(s):[/bold red]\n")

    if "deprecated" in issues:
        table = Table(title="Deprecated Objects", show_lines=True)
        table.add_column("Object", style="cyan")
        table.add_column("Message", style="yellow")
        table.add_column("Replacement", style="green")
        for item in issues["deprecated"]:
            table.add_row(item["object"], item["message"], item.get("replacement", ""))
        console.print(table)
        console.print()

    if "missing_integrity" in issues:
        table = Table(title="Missing Integrity Checksums", show_lines=True)
        table.add_column("Object", style="cyan")
        table.add_column("Release", style="blue")
        table.add_column("Missing Field", style="yellow")
        for item in issues["missing_integrity"]:
            table.add_row(item["object"], item["release"], item["field"])
        console.print(table)
        console.print()

    if "missing_dependencies" in issues:
        table = Table(title="Missing Dependencies", show_lines=True)
        table.add_column("Object", style="cyan")
        table.add_column("Dependency", style="red")
        table.add_column("Reason", style="yellow")
        for item in issues["missing_dependencies"]:
            table.add_row(item["object"], item["dependency"], item["reason"])
        console.print(table)
        console.print()

    if "missing_peer_dependencies" in issues:
        table = Table(title="Missing Peer Dependencies", show_lines=True)
        table.add_column("Object", style="cyan")
        table.add_column("Peer", style="red")
        table.add_column("Reason", style="yellow")
        for item in issues["missing_peer_dependencies"]:
            table.add_row(item["object"], item["peer"], item["reason"])
        console.print(table)
        console.print()

    if "unresolvable_optional" in issues:
        table = Table(title="Unresolvable Optional Dependencies", show_lines=True)
        table.add_column("Object", style="cyan")
        table.add_column("Optional Dep", style="yellow")
        table.add_column("Reason", style="dim")
        for item in issues["unresolvable_optional"]:
            table.add_row(item["object"], item["optional"], item["reason"])
        console.print(table)
        console.print()

    if "conflicts" in issues:
        table = Table(title="Version Conflicts", show_lines=True)
        table.add_column("Dependency", style="red")
        table.add_column("Requirer A", style="cyan")
        table.add_column("Constraint A", style="yellow")
        table.add_column("Requirer B", style="cyan")
        table.add_column("Constraint B", style="yellow")
        table.add_column("Resolved", style="dim")
        for item in issues["conflicts"]:
            table.add_row(
                item["dependency"],
                item["requirer_a"], item["constraint_a"],
                item["requirer_b"], item["constraint_b"],
                item.get("resolved_version", ""),
            )
        console.print(table)
        console.print()
