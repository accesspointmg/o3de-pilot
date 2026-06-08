# O3DE Pilot CLI - Publish Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Publish and validation commands for O3DE objects."""

import click
import json
import tarfile
import hashlib
import io
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
SCHEMA_BASE_URL = "https://canonical.o3de.org"
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


@publish.command("pack")
@click.argument("path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), help="Output tarball path (default: <name>-<version>.tar.gz)")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
def pack_command(path: str, output: str | None, as_json: bool) -> None:
    """Package an O3DE object directory into a distributable tarball.

    Creates a .tar.gz archive containing the object JSON and all
    associated files. Computes SHA-256 integrity hash for the archive.

    PATH is the directory containing the O3DE object (engine.json, gem.json, etc.).
    """
    target = Path(path)

    # Validate first
    errors, warnings = validate_object(target)
    if errors:
        if as_json:
            console.print_json(json.dumps({"status": "error", "errors": errors}))
        else:
            console.print(Panel("\n".join(f"[red]ERROR:[/red] {e}" for e in errors),
                                title="Validation Failed", border_style="red"))
        raise SystemExit(1)

    # Determine name and version from the object JSON
    obj_dir = target if target.is_dir() else target.parent
    json_path, data = _find_object_json(obj_dir)
    if json_path is None:
        console.print("[red]No O3DE object JSON found.[/red]")
        raise SystemExit(1)

    obj_type = get_object_type(data)
    name = get_object_name(data)
    version = get_object_version(data)

    if not name or not version:
        console.print("[red]Object must have name and version for packaging.[/red]")
        raise SystemExit(1)

    # Build tarball
    safe_name = name.replace(".", "-")
    archive_name = f"{safe_name}-{version}.tar.gz"
    if output:
        archive_path = Path(output)
    else:
        archive_path = obj_dir.parent / archive_name

    archive_path.parent.mkdir(parents=True, exist_ok=True)

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(str(obj_dir), arcname=f"{safe_name}-{version}")

    # Compute SHA-256
    sha256 = compute_sha256(archive_path)

    if as_json:
        console.print_json(json.dumps({
            "status": "ok",
            "data": {
                "archive": str(archive_path),
                "name": name,
                "version": version,
                "type": obj_type.value,
                "sha256": sha256,
                "size_bytes": archive_path.stat().st_size,
            },
        }))
    else:
        console.print(f"[green]Packed:[/green] {archive_path}")
        console.print(f"  Name:    {name}")
        console.print(f"  Version: {version}")
        console.print(f"  Type:    {obj_type.value}")
        console.print(f"  SHA-256: {sha256}")
        console.print(f"  Size:    {archive_path.stat().st_size:,} bytes")


@publish.command("push")
@click.argument("path", type=click.Path(exists=True))
@click.option("--remote", "-r", help="Remote repo URL to push to")
@click.option("--dry-run", is_flag=True, help="Validate without pushing")
@click.option("--force", is_flag=True, help="Overwrite existing version (bypass immutability)")
@click.option("--json", "as_json", is_flag=True, help="Output results as JSON")
def push_command(path: str, remote: str | None, dry_run: bool, force: bool, as_json: bool) -> None:
    """Validate and publish an O3DE object to a remote repo.

    Validates the object JSON, checks integrity fields, enforces
    version immutability, then pushes the object metadata to the
    specified remote repository.
    """
    target = Path(path)
    errors, warnings = validate_object(target)

    if errors:
        if as_json:
            console.print_json(json.dumps({"status": "error", "errors": errors}))
        else:
            console.print(Panel("\n".join(f"[red]ERROR:[/red] {e}" for e in errors),
                                title="Validation Failed", border_style="red"))
            console.print("[red]Cannot publish — fix validation errors first.[/red]")
        raise SystemExit(1)

    if warnings:
        for w in warnings:
            console.print(f"[yellow]WARN:[/yellow] {w}")

    # Extract object metadata
    obj_dir = target if target.is_dir() else target.parent
    json_path, data = _find_object_json(obj_dir)
    if json_path is None:
        console.print("[red]No O3DE object JSON found.[/red]")
        raise SystemExit(1)

    obj_type = get_object_type(data)
    name = get_object_name(data)
    version = get_object_version(data)

    if dry_run:
        msg = f"Validation passed. Would publish {name}@{version} ({obj_type.value})"
        if as_json:
            console.print_json(json.dumps({
                "status": "ok",
                "dry_run": True,
                "data": {"name": name, "version": version, "type": obj_type.value},
            }))
        else:
            console.print(f"[yellow]Dry-run:[/yellow] {msg}")
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
        msg = "No remote specified. Use --remote or configure a remote."
        if as_json:
            console.print_json(json.dumps({"status": "error", "errors": [msg]}))
        else:
            console.print(f"[red]{msg}[/red]")
        raise SystemExit(1)

    # Version immutability check
    immutability_error = _check_version_immutability(remote, name, version, obj_type)
    if immutability_error and not force:
        msg = f"Version {version} of {name} already exists at {remote}. Use --force to overwrite."
        if as_json:
            console.print_json(json.dumps({"status": "error", "errors": [msg]}))
        else:
            console.print(f"[red]{msg}[/red]")
        raise SystemExit(1)

    # Upload to remote
    upload_result = _upload_to_remote(remote, data, obj_type, name, version)

    if upload_result.get("error"):
        if as_json:
            console.print_json(json.dumps({"status": "error", "errors": [upload_result["error"]]}))
        else:
            console.print(f"[red]Upload failed: {upload_result['error']}[/red]")
        raise SystemExit(1)

    if as_json:
        console.print_json(json.dumps({
            "status": "ok",
            "data": {
                "name": name,
                "version": version,
                "type": obj_type.value,
                "remote": remote,
            },
        }))
    else:
        console.print(f"[bold]Published to:[/bold] {remote}")
        console.print(f"[green]Published {name}@{version} successfully.[/green]")


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


def _find_object_json(obj_dir: Path) -> tuple[Path | None, dict | None]:
    """Find and load the O3DE object JSON from a directory."""
    for type_name in ["engine", "project", "gem", "template", "repo", "overlay"]:
        for pattern in [f"{type_name}.2-0-0.json", f"{type_name}.json"]:
            candidate = obj_dir / pattern
            if candidate.exists():
                with open(candidate) as f:
                    return candidate, json.load(f)
    return None, None


def _check_version_immutability(
    remote: str, name: str, version: str, obj_type: ObjectType
) -> bool:
    """Check if a version already exists at the remote.

    Returns True if the version exists (immutability violation), False otherwise.
    """
    import urllib.parse

    parsed = urllib.parse.urlparse(remote)

    # For local/file remotes, check filesystem directly
    if parsed.scheme in ("", "file") or (len(parsed.scheme) == 1 and parsed.scheme.isalpha()):
        repo_path = Path(remote) if parsed.scheme != "file" else Path(parsed.path)
        type_plural = {
            ObjectType.ENGINE: "engines",
            ObjectType.PROJECT: "projects",
            ObjectType.GEM: "gems",
            ObjectType.TEMPLATE: "templates",
        }.get(obj_type, f"{obj_type.value}s")
        safe_name = name.replace(".", "-")
        obj_json = repo_path / type_plural / safe_name / version / f"{obj_type.value}.2-0-0.json"
        return obj_json.exists()

    # For HTTP remotes, use the Store
    try:
        from o3de_pilot.core.store import Store
        store = Store()
        store.refresh_sync([remote])
        existing = store.get_version(obj_type, name, version)
        return existing is not None
    except Exception:
        return False


def _upload_to_remote(
    remote: str, data: dict, obj_type: ObjectType, name: str, version: str
) -> dict:
    """Upload object metadata to a remote repository.

    For git-based remotes, this creates/updates the object entry in the
    repo JSON. For HTTP registries, this POSTs the object metadata.

    Returns dict with 'ok' or 'error' key.
    """
    import urllib.parse

    parsed = urllib.parse.urlparse(remote)

    if parsed.scheme in ("http", "https"):
        return _upload_http(remote, data, obj_type, name, version)
    elif parsed.scheme in ("", "file") or (len(parsed.scheme) == 1 and parsed.scheme.isalpha()):
        # Empty scheme, file:// scheme, or single-letter scheme (Windows drive letter)
        return _upload_local(remote, data, obj_type, name, version)
    else:
        return {"error": f"Unsupported remote scheme: {parsed.scheme}"}


def _upload_http(
    remote: str, data: dict, obj_type: ObjectType, name: str, version: str
) -> dict:
    """Upload object to an HTTP registry endpoint.

    Expected API: PUT {remote}/api/v1/objects/{type}/{name}/{version}
    """
    import urllib.request
    import urllib.error

    url = f"{remote.rstrip('/')}/api/v1/objects/{obj_type.value}/{name}/{version}"
    payload = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="PUT",
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status in (200, 201):
                return {"ok": True}
            return {"error": f"HTTP {resp.status}"}
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return {"error": f"Version {version} already exists (HTTP 409 Conflict)"}
        return {"error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}


def _upload_local(
    remote: str, data: dict, obj_type: ObjectType, name: str, version: str
) -> dict:
    """Upload object to a local/file-based repository.

    Writes the object JSON into the repo directory structure:
    {remote}/{type_plural}/{name}/{version}/{type}.2-0-0.json
    """
    import urllib.parse

    parsed = urllib.parse.urlparse(remote)
    if parsed.scheme == "file":
        repo_path = Path(parsed.path)
    else:
        repo_path = Path(remote)

    type_plural = {
        ObjectType.ENGINE: "engines",
        ObjectType.PROJECT: "projects",
        ObjectType.GEM: "gems",
        ObjectType.TEMPLATE: "templates",
        ObjectType.REPO: "repos",
        ObjectType.OVERLAY: "overlays",
    }.get(obj_type, f"{obj_type.value}s")

    safe_name = name.replace(".", "-")
    obj_dir = repo_path / type_plural / safe_name / version
    obj_dir.mkdir(parents=True, exist_ok=True)

    json_path = obj_dir / f"{obj_type.value}.2-0-0.json"
    with open(json_path, "w") as f:
        json.dump(data, f, indent=2)

    # Update the repo index
    _update_repo_index(repo_path, data, obj_type)

    return {"ok": True}


def _update_repo_index(repo_path: Path, data: dict, obj_type: ObjectType) -> None:
    """Update the repo.2-0-0.json index with the new object."""
    index_path = repo_path / "repo.2-0-0.json"

    if index_path.exists():
        with open(index_path) as f:
            index = json.load(f)
    else:
        index = {
            "$schemaVersion": "2.0.0",
            "$schema": f"{SCHEMA_BASE_URL}/o3de-repo-2.0.0.json",
            "repo": {"name": repo_path.name},
            "engines": [],
            "projects": [],
            "gems": [],
            "templates": [],
        }

    type_plural = {
        ObjectType.ENGINE: "engines",
        ObjectType.PROJECT: "projects",
        ObjectType.GEM: "gems",
        ObjectType.TEMPLATE: "templates",
    }.get(obj_type)

    if type_plural and type_plural in index:
        # Check for duplicate
        name = get_object_name(data)
        version = get_object_version(data)
        existing = [
            obj for obj in index[type_plural]
            if get_object_name(obj) == name and get_object_version(obj) == version
        ]
        if not existing:
            index[type_plural].append(data)

    with open(index_path, "w") as f:
        json.dump(index, f, indent=2)
