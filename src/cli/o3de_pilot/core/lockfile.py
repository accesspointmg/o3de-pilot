# O3DE Pilot - Lockfile
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Lockfile support for reproducible dependency resolution.

A lockfile records the exact resolved versions of all dependencies
for a workspace, similar to package-lock.json or Cargo.lock.

File: workspace-lock.json (placed next to workspace.json)
"""

import json
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LOCKFILE_NAME = "workspace-lock.json"
LOCKFILE_VERSION = "1"


def generate_lockfile(
    workspace_path: Path,
    resolved_candidates: dict,
    root_name: str,
    root_version: str,
) -> Path:
    """Generate a lockfile from resolved dependency candidates.

    Args:
        workspace_path: Path to the workspace directory
        resolved_candidates: Dict of {name: candidate_info} from the solver
        root_name: Name of the root object
        root_version: Version of the root object

    Returns:
        Path to the generated lockfile
    """
    packages = {}
    for name, candidate in resolved_candidates.items():
        entry = {
            "version": _get_version(candidate),
            "type": _get_type(candidate),
        }
        path = _get_path(candidate)
        if path:
            entry["path"] = str(path)
        sha256 = _get_sha256(candidate)
        if sha256:
            entry["sha256"] = sha256
        source = _get_source(candidate)
        if source:
            entry["source"] = source
        packages[name] = entry

    lockfile_data = {
        "lockfileVersion": LOCKFILE_VERSION,
        "root": root_name,
        "rootVersion": root_version,
        "generated": datetime.now(timezone.utc).isoformat(),
        "contentHash": _compute_content_hash(packages),
        "packages": packages,
    }

    lockfile_path = workspace_path / LOCKFILE_NAME
    with open(lockfile_path, "w") as f:
        json.dump(lockfile_data, f, indent=2)

    logger.info(f"Lockfile written to {lockfile_path}")
    return lockfile_path


def read_lockfile(workspace_path: Path) -> Optional[dict]:
    """Read a lockfile from a workspace directory.

    Returns None if no lockfile exists.
    """
    lockfile_path = workspace_path / LOCKFILE_NAME
    if not lockfile_path.exists():
        return None
    with open(lockfile_path) as f:
        return json.load(f)


def verify_lockfile(
    workspace_path: Path,
    resolved_candidates: dict,
) -> tuple[bool, list[str]]:
    """Verify that current resolution matches the lockfile.

    Args:
        workspace_path: Path to the workspace directory
        resolved_candidates: Current resolved candidates from solver

    Returns:
        Tuple of (matches, mismatches) where mismatches is a list of descriptions
    """
    lockdata = read_lockfile(workspace_path)
    if lockdata is None:
        return False, ["No lockfile found"]

    locked_packages = lockdata.get("packages", {})
    mismatches = []

    # Check each locked package against current resolution
    for name, locked in locked_packages.items():
        if name not in resolved_candidates:
            mismatches.append(f"{name}: locked at {locked['version']} but not in current resolution")
            continue
        current = resolved_candidates[name]
        current_version = _get_version(current)
        if current_version != locked["version"]:
            mismatches.append(
                f"{name}: locked at {locked['version']} but resolved to {current_version}"
            )

    # Check for new packages not in lockfile
    for name in resolved_candidates:
        if name not in locked_packages:
            current = resolved_candidates[name]
            mismatches.append(
                f"{name}: resolved to {_get_version(current)} but not in lockfile"
            )

    return len(mismatches) == 0, mismatches


def _compute_content_hash(packages: dict) -> str:
    """Compute a hash of the package set for quick comparison."""
    canonical = json.dumps(
        {k: {"version": v["version"], "type": v["type"]} for k, v in sorted(packages.items())},
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _get_version(candidate) -> str:
    """Extract version from a candidate (dict or object)."""
    if isinstance(candidate, dict):
        return candidate.get("version", "")
    return getattr(candidate, "version", "")


def _get_type(candidate) -> str:
    """Extract type from a candidate."""
    if isinstance(candidate, dict):
        t = candidate.get("type", candidate.get("object_type", ""))
        return t.value if hasattr(t, "value") else str(t)
    t = getattr(candidate, "object_type", getattr(candidate, "type", ""))
    return t.value if hasattr(t, "value") else str(t)


def _get_path(candidate) -> Optional[str]:
    """Extract path from a candidate."""
    if isinstance(candidate, dict):
        return candidate.get("path")
    p = getattr(candidate, "path", None)
    return str(p) if p else None


def _get_sha256(candidate) -> Optional[str]:
    """Extract SHA-256 from a candidate."""
    if isinstance(candidate, dict):
        return candidate.get("sha256")
    return getattr(candidate, "sha256", None)


def _get_source(candidate) -> Optional[str]:
    """Extract source URL from a candidate."""
    if isinstance(candidate, dict):
        return candidate.get("source")
    return getattr(candidate, "source", None)
