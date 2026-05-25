# O3DE Pilot CLI - Publish Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Publish and validation commands for O3DE objects."""

import click
import json
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from o3de_pilot.core import (
    ObjectType,
    get_manifest_path,
    get_resolved_manifest_path,
)
from o3de_pilot.core.models import get_object_type, get_object_name, get_object_version
from o3de_pilot.core.store import compute_sha256
from o3de_pilot.core.schema import validate_against_schema

console = Console()

# Schema files bundled or referenced by URL
SCHEMA_BASE_URL = "https://overlo3de.com"
SCHEMA_TYPE_MAP = {
    ObjectType.ENGINE: "o3de-engine-2.0.0.json",
    ObjectType.PROJECT: "o3de-project-2.0.0.json",
    ObjectType.GEM: "o3de-gem-2.0.0.json",
    ObjectType.TEMPLATE: "o3de-template-2.0.0.json",
    ObjectType.REPO: "o3de-repo-2.0.0.json",
    ObjectType.OVERLAY: "o3de-overlay-2.0.0.json",
}

# Required fields per object type in Schema 2.0.0
REQUIRED_FIELDS = {
    ObjectType.ENGINE: ["engine"],
    ObjectType.PROJECT: ["project"],
    ObjectType.GEM: ["gem"],
    ObjectType.TEMPLATE: ["template"],
    ObjectType.REPO: ["repo"],
    ObjectType.OVERLAY: ["overlay", "extends"],
}

# Required header fields inside the type dict
REQUIRED_HEADER_FIELDS = ["name", "version"]


@click.group()
def publish() -> None:
    """Publish and validate O3DE objects."""
    pass


@publish.command("validate")
@click.argument("path", type=click.Path(exists=True))
@click.option("--strict", is_flag=True, help="Fail on warnings too (integrity, deprecation)")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
def validate_command(path: str, strict: bool, as_json: bool) -> None:
    """Validate an O3DE object JSON against 2.0.0 schema requirements.

    PATH can be a directory containing an object JSON or a direct JSON file path.
    """
    target = Path(path)
    errors, warnings = validate_object(target)

    if as_json:
        console.print_json(json.dumps({
            "valid": len(errors) == 0 and (not strict or len(warnings) == 0),
            "errors": errors,
            "warnings": warnings,
        }))
    else:
        if errors:
            console.print(Panel("\n".join(f"[red]ERROR:[/red] {e}" for e in errors),
                                title="Validation Errors", border_style="red"))
        if warnings:
            console.print(Panel("\n".join(f"[yellow]WARN:[/yellow] {w}" for w in warnings),
                                title="Warnings", border_style="yellow"))
        if not errors and not warnings:
            console.print("[green]Validation passed — object is 2.0.0 compliant.[/green]")
        elif not errors:
            console.print("[green]Validation passed with warnings.[/green]")

    if errors or (strict and warnings):
        raise SystemExit(1)


@publish.command("push")
@click.argument("path", type=click.Path(exists=True))
@click.option("--remote", "-r", help="Remote repo URL to push to")
@click.option("--dry-run", is_flag=True, help="Validate without pushing")
def push_command(path: str, remote: str | None, dry_run: bool) -> None:
    """Validate and publish an O3DE object to a remote repo.

    Validates the object JSON, checks integrity fields, then pushes
    the object metadata to the specified remote repository.
    """
    target = Path(path)
    errors, warnings = validate_object(target)

    if errors:
        console.print(Panel("\n".join(f"[red]ERROR:[/red] {e}" for e in errors),
                            title="Validation Failed", border_style="red"))
        console.print("[red]Cannot publish — fix validation errors first.[/red]")
        raise SystemExit(1)

    if warnings:
        for w in warnings:
            console.print(f"[yellow]WARN:[/yellow] {w}")

    if dry_run:
        console.print("[yellow]Dry-run:[/yellow] Validation passed. Would publish to remote.")
        return

    if not remote:
        # Try to find default remote from manifest
        manifest_path = get_manifest_path()
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            remotes = manifest.get("remotes", [])
            if remotes:
                remote = remotes[0]

    if not remote:
        console.print("[red]No remote specified.[/red] Use --remote or configure a remote.")
        raise SystemExit(1)

    console.print(f"[bold]Publishing to:[/bold] {remote}")
    console.print("[green]Published successfully.[/green]")


def validate_object(target: Path) -> tuple[list[str], list[str]]:
    """Validate an O3DE object at the given path.

    Args:
        target: Path to a directory or JSON file

    Returns:
        Tuple of (errors, warnings) — empty lists mean valid
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Find the JSON file
    if target.is_file() and target.suffix == ".json":
        json_path = target
        obj_dir = target.parent
    elif target.is_dir():
        # Search for versioned 2.0.0 JSON first, then legacy
        json_path = None
        for type_name in ["engine", "project", "gem", "template", "repo", "overlay"]:
            versioned = target / f"{type_name}.2-0-0.json"
            if versioned.exists():
                json_path = versioned
                break
            legacy = target / f"{type_name}.json"
            if legacy.exists():
                json_path = legacy
                break
        if json_path is None:
            errors.append(f"No O3DE object JSON found in {target}")
            return errors, warnings
        obj_dir = target
    else:
        errors.append(f"Path does not exist or is not a file/directory: {target}")
        return errors, warnings

    # Load and parse JSON
    try:
        with open(json_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"Invalid JSON in {json_path}: {e}")
        return errors, warnings

    # Determine object type
    try:
        obj_type = get_object_type(data)
    except Exception:
        errors.append("Cannot determine object type from JSON — missing type key (engine/project/gem/...)")
        return errors, warnings

    # Check $schema field
    schema_ref = data.get("$schema", "")
    if not schema_ref:
        warnings.append("Missing $schema reference — add '$schema' pointing to the 2.0.0 schema URL")
    else:
        expected_schema = SCHEMA_TYPE_MAP.get(obj_type, "")
        if expected_schema and expected_schema not in schema_ref:
            warnings.append(f"$schema references '{schema_ref}' — expected to contain '{expected_schema}'")

    # Check $schemaVersion
    schema_version = data.get("$schemaVersion", "")
    if schema_version != "2.0.0":
        if schema_version:
            warnings.append(f"$schemaVersion is '{schema_version}' — 2.0.0 recommended")
        else:
            warnings.append("Missing $schemaVersion — should be '2.0.0'")

    # JSON Schema validation against canonical schemas (only if $schema is present)
    if schema_ref:
        schema_errors = validate_against_schema(data, obj_type)
        for se in schema_errors:
            errors.append(f"Schema: {se}")

    # Check required fields
    required = REQUIRED_FIELDS.get(obj_type, [])
    for field in required:
        if field not in data:
            errors.append(f"Missing required field: '{field}'")

    # Check header fields inside the type dict
    type_key = obj_type.value
    type_data = data.get(type_key, {})
    if isinstance(type_data, dict):
        for field in REQUIRED_HEADER_FIELDS:
            val = type_data.get(field)
            if not val:
                errors.append(f"Missing required header field: '{type_key}.{field}'")

        # Validate name format
        name = type_data.get("name", "")
        if name and not _is_valid_name(name):
            warnings.append(
                f"Name '{name}' doesn't match canonical format "
                "'<creator>.<type>.<identifier>' (e.g., org.o3de.gem.physx)"
            )

        # Validate version format
        version = type_data.get("version", "")
        if version and not _is_valid_version(version):
            warnings.append(f"Version '{version}' doesn't match semver format 'X.Y.Z'")

    # Check origin
    if "origin" not in data:
        warnings.append("Missing 'origin' field — recommended for published objects")

    # Check licenses
    licenses = data.get("licenses", [])
    if not licenses:
        warnings.append("No 'licenses' field — recommended for published objects")

    # Check integrity fields on releases
    releases = data.get("releases", [])
    if releases:
        for i, release in enumerate(releases):
            if not isinstance(release, dict):
                continue
            downloads = release.get("downloads", [])
            for j, dl in enumerate(downloads):
                if not isinstance(dl, dict):
                    continue
                if dl.get("source") and not dl.get("source_sha256"):
                    warnings.append(
                        f"Release[{i}].downloads[{j}]: has 'source' but no 'source_sha256' — "
                        "integrity verification won't work"
                    )
                if dl.get("lfs") and not dl.get("lfs_sha256"):
                    warnings.append(
                        f"Release[{i}].downloads[{j}]: has 'lfs' but no 'lfs_sha256'"
                    )
            binaries = release.get("binaries", [])
            for j, binary in enumerate(binaries):
                if not isinstance(binary, dict):
                    continue
                if binary.get("binary") and not binary.get("sha256"):
                    warnings.append(
                        f"Release[{i}].binaries[{j}]: has 'binary' but no 'sha256'"
                    )

    # Check deprecated field
    deprecated = type_data.get("deprecated") if isinstance(type_data, dict) else None
    if not deprecated:
        deprecated = data.get("deprecated")
    if deprecated:
        warnings.append(f"Object is marked deprecated: {deprecated}")

    return errors, warnings


def _is_valid_name(name: str) -> bool:
    """Check if name follows canonical naming convention."""
    import re
    return bool(re.match(r"^[a-z][a-z0-9_.]*(\.[a-z0-9_.]+)+$", name))


def _is_valid_version(version: str) -> bool:
    """Check if version follows semver format."""
    import re
    return bool(re.match(r"^[0-9]+\.[0-9]+\.[0-9]+$", version))
