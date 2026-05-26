# O3DE Pilot CLI - JSON Schema Validation
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""JSON Schema validation against canonical 2.0.0 schemas."""

import json
import logging
from pathlib import Path
from typing import Optional

from o3de_pilot.core.models import ObjectType

logger = logging.getLogger(__name__)

# Map object types to their canonical schema filenames
SCHEMA_FILENAMES = {
    ObjectType.ENGINE: "o3de-engine-2.0.0.json",
    ObjectType.PROJECT: "o3de-project-2.0.0.json",
    ObjectType.GEM: "o3de-gem-2.0.0.json",
    ObjectType.TEMPLATE: "o3de-template-2.0.0.json",
    ObjectType.REPO: "o3de-repo-2.0.0.json",
    ObjectType.OVERLAY: "o3de-overlay-2.0.0.json",
}

# Workspace schema filename — not keyed by ObjectType since workspace
# is not an O3DE object type, just a local build artifact.
WORKSPACE_SCHEMA_FILENAME = "o3de-workspace-2.0.0.json"


class SchemaValidationError(Exception):
    """Raised when JSON Schema validation fails."""
    pass


def find_schema_directory() -> Optional[Path]:
    """Try to locate the canonical schema directory.

    Searches common locations for the canonical.o3de.org/src/ directory.
    """
    # Check environment variable first
    import os
    env_path = os.environ.get("O3DE_SCHEMA_DIR")
    if env_path:
        p = Path(env_path)
        if p.is_dir():
            return p

    # Walk up from this file looking for canonical.o3de.org sibling
    current = Path(__file__).resolve().parent
    for _ in range(10):
        candidate = current / "canonical.o3de.org" / "src"
        if candidate.is_dir():
            return candidate
        candidate = current.parent / "canonical.o3de.org" / "src"
        if candidate.is_dir():
            return candidate
        current = current.parent

    return None


def validate_against_schema(
    data: dict,
    obj_type: ObjectType,
    schema_dir: Optional[Path] = None,
) -> list[str]:
    """Validate object data against its canonical JSON Schema.

    Args:
        data: The parsed JSON object data.
        obj_type: The O3DE object type.
        schema_dir: Directory containing the canonical schema files.
                     If None, tries to auto-detect.

    Returns:
        List of validation error messages (empty = valid).
    """
    try:
        import jsonschema
        import referencing
        import referencing.jsonschema
    except ImportError:
        return ["jsonschema package not installed — run: pip install jsonschema"]

    schema_filename = SCHEMA_FILENAMES.get(obj_type)
    if not schema_filename:
        return [f"No canonical schema defined for object type: {obj_type.value}"]

    if schema_dir is None:
        schema_dir = find_schema_directory()

    if schema_dir is None or not schema_dir.is_dir():
        return ["Cannot find canonical schema directory — set O3DE_SCHEMA_DIR or install canonical.o3de.org"]

    schema_path = schema_dir / schema_filename
    if not schema_path.exists():
        return [f"Schema file not found: {schema_path}"]

    # Load the schema
    try:
        with open(schema_path) as f:
            schema = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        return [f"Failed to load schema {schema_path}: {e}"]

    # Build a registry that can follow $ref to patterns and other schemas
    resources = []
    for json_file in schema_dir.glob("*.json"):
        try:
            with open(json_file) as f:
                s = json.load(f)
            if not isinstance(s, dict):
                continue
            schema_id = s.get("$id", f"./{json_file.name}")
            resource = referencing.Resource.from_contents(
                s, default_specification=referencing.jsonschema.DRAFT7,
            )
            resources.append((schema_id, resource))
        except (json.JSONDecodeError, OSError):
            continue

    registry = referencing.Registry().with_resources(resources)

    # Validate
    validator = jsonschema.Draft7Validator(schema, registry=registry)
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in error.absolute_path) or "(root)"
        errors.append(f"[{path}] {error.message}")

    return errors
