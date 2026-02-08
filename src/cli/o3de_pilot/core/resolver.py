# O3DE Pilot - Manifest Resolver
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Manifest Resolver.

The resolver:
1. Loads the manifest (o3de_manifest.json)
2. Descends all local object paths, reading their JSON
3. Resolves children from parent objects
4. Flattens everything into resolved_o3de_manifest.json

Resolution also handles:
- Dependency resolution using resolvelib (semver constraints)
- Overlay matching to base objects
- Deduplication of objects found via multiple paths
"""

from pathlib import Path
from typing import Optional, Callable, Any
from packaging.version import Version
from packaging.specifiers import SpecifierSet
import json
import logging
import re
import hashlib

from .paths import (
    get_manifest_path,
    get_resolved_manifest_path,
    get_object_json_filename,
    get_versioned_object_json_filename,
    find_object_json,
)
from .models import (
    O3DEObject, ObjectType, Manifest, Engine, Project, Gem, Template, Repo, Overlay,
    Children, LocalObjects, Remote,
    get_object_type, get_object_name, get_object_version,
)
from .upgrade import (
    get_schema_version,
    needs_upgrade,
    upgrade_to_latest,
)
from .git_utils import (
    get_local_git_remote,
    get_local_git_branch,
)

logger = logging.getLogger("o3de_pilot.resolver")


def compute_file_hash(path: Path) -> str:
    """
    Compute SHA-256 hash of a file.
    
    Args:
        path: Path to the file
        
    Returns:
        Hex digest of the file's SHA-256 hash, or empty string if file not readable
    """
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except (OSError, IOError):
        return ""


class ResolverError(Exception):
    """Error during resolution."""
    pass


class ObjectNameVersion:
    """Parsed object name with optional version constraint."""
    
    def __init__(self, specifier: str):
        """
        Parse a specifier like:
        - "org.o3de.gem.physx" (any version)
        - "org.o3de.gem.physx==1.0.0" (exact version)
        - "org.o3de.gem.physx>=1.0.0" (minimum version)
        - "org.o3de.gem.physx>=1.0.0<2.0.0" (range)
        """
        self.original = specifier
        
        # Try to parse version constraint
        match = re.match(
            r"^([a-z][a-z0-9_.]+)((?:==|>=|>|<=|<)[0-9.]+(?:(?:<=|<)[0-9.]+)?)?$",
            specifier
        )
        
        if match:
            self.name = match.group(1)
            version_part = match.group(2) or ""
            
            if version_part:
                # Convert to packaging specifier format
                # >=1.0.0<2.0.0 -> >=1.0.0,<2.0.0
                version_part = re.sub(r"(<|<=|>|>=)", r",\1", version_part).lstrip(",")
                self.specifier = SpecifierSet(version_part)
            else:
                self.specifier = SpecifierSet()  # Matches any version
        else:
            self.name = specifier
            self.specifier = SpecifierSet()
    
    def matches(self, version: str) -> bool:
        """Check if a version matches this constraint."""
        if not self.specifier:
            return True
        
        try:
            return Version(version) in self.specifier
        except Exception:
            return True  # If version is invalid, accept it
    
    def __repr__(self) -> str:
        if self.specifier:
            return f"{self.name}{self.specifier}"
        return self.name


class ResolvedObject:
    """A resolved O3DE object with full path and parsed data."""
    
    def __init__(
        self,
        path: Path,
        object_type: ObjectType,
        name: str,
        version: str,
        data: dict,
    ):
        self.path = path
        self.object_type = object_type
        self.name = name
        self.version = version
        self.data = data
        
        # Children discovered from this object
        self.children: list["ResolvedObject"] = []
        
        # Dependencies (parsed from data)
        self.dependencies: list[ObjectNameVersion] = []
        
        # Overlays that extend this object
        self.overlays: list["ResolvedObject"] = []
        
        # Parent object that contains this one (set during resolution)
        self.parent: Optional["ResolvedObject"] = None
    
    def __repr__(self) -> str:
        return f"ResolvedObject({self.object_type.value}:{self.name}@{self.version})"


class Resolver:
    """
    Resolves the O3DE manifest into a complete, flattened view.
    
    Usage:
        resolver = Resolver()
        resolved = resolver.resolve()
        resolver.save()
    """
    
    def __init__(self, manifest_path: Optional[Path] = None):
        self.manifest_path = manifest_path or get_manifest_path()
        self.resolved_path = get_resolved_manifest_path()
        
        # All resolved objects by name
        self.objects: dict[str, ResolvedObject] = {}
        
        # Objects by type
        self.engines: dict[str, ResolvedObject] = {}
        self.projects: dict[str, ResolvedObject] = {}
        self.gems: dict[str, ResolvedObject] = {}
        self.templates: dict[str, ResolvedObject] = {}
        self.repos: dict[str, ResolvedObject] = {}
        self.overlays: dict[str, ResolvedObject] = {}
        
        # Manifest data
        self.manifest_data: Optional[dict] = None
        
        # File hashes for change detection: path -> hash
        self.file_hashes: dict[str, str] = {}
    
    def resolve(
        self,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> dict[str, ResolvedObject]:
        """
        Resolve the manifest.
        
        1. Load manifest JSON
        2. Descend all local object paths
        3. Resolve children recursively
        4. Parse dependencies
        5. Match overlays to base objects
        
        Returns:
            Dict of object_name -> ResolvedObject
        """
        if not self.manifest_path.exists():
            raise ResolverError(f"Manifest not found: {self.manifest_path}")
        
        # Load manifest and compute hash
        with open(self.manifest_path, "r") as f:
            self.manifest_data = json.load(f)
        manifest_hash = compute_file_hash(self.manifest_path)
        if manifest_hash:
            self.file_hashes[self.manifest_path.as_posix()] = manifest_hash
        
        # Handle both Schema 2.0.0 (local.engines) and legacy (engines at root) formats
        local = self.manifest_data.get("local", {})
        
        # Note: We do NOT convert "restricteds" to "overlays"
        # They are different concepts with no upgrade path
        
        # Collect all root paths to resolve
        root_paths = []
        stale_paths = []  # Track paths that don't exist
        for obj_type in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
            # Schema 2.0.0: local.engines, local.projects, etc.
            paths = local.get(obj_type, [])
            # Legacy: engines, projects, etc. at root level
            if not paths:
                paths = self.manifest_data.get(obj_type, []) or []
            for path_str in paths:
                p = Path(path_str)
                # Check if path exists (handle both file and directory paths)
                if p.is_file():
                    check_path = p.parent
                else:
                    check_path = p
                if not check_path.exists():
                    stale_paths.append((path_str, obj_type))
                    logger.warning(f"Removing stale path from manifest: {path_str}")
                else:
                    root_paths.append((p, obj_type))
        
        # Remove stale paths from manifest
        if stale_paths:
            self._remove_stale_paths(stale_paths)
        
        total = len(root_paths)
        current = 0
        
        # Resolve each root object
        for path, obj_type_str in root_paths:
            current += 1
            
            if progress_callback:
                progress_callback(f"Resolving {path.name}", current, total)
            
            self._resolve_object(path, ObjectType(obj_type_str.rstrip("s")))
        
        # Match overlays to base objects
        self._match_overlays()
        
        if progress_callback:
            progress_callback("Complete", total, total)
        
        logger.info(f"Resolved {len(self.objects)} objects")
        return self.objects
    
    def _resolve_object(self, path: Path, expected_type: ObjectType) -> Optional[ResolvedObject]:
        """Resolve a single object and its children."""
        if not path.exists():
            logger.warning(f"Object path does not exist: {path}")
            return None
        
        # Handle paths pointing directly to JSON files
        if path.is_file() and path.suffix == '.json':
            original_json_path = path
            is_versioned = '.2-0-0.' in path.name or '-2-0-0.' in path.name
            # Use parent directory as the object root
            path = path.parent
            
            # If legacy file, check if versioned file exists and prefer it
            if not is_versioned:
                try:
                    versioned_path, _ = find_object_json(path, expected_type.value)
                    if versioned_path != original_json_path:
                        json_path = versioned_path
                        is_versioned = True
                    else:
                        json_path = original_json_path
                except FileNotFoundError:
                    json_path = original_json_path
            else:
                json_path = original_json_path
        else:
            # Find the object JSON - prefer versioned 2.0.0 file over legacy
            try:
                json_path, is_versioned = find_object_json(path, expected_type.value)
            except FileNotFoundError:
                # Try to detect type from existing JSON files
                json_path = None
                is_versioned = False
                for type_name in ["engine", "project", "gem", "template", "repo", "overlay"]:
                    try:
                        json_path, is_versioned = find_object_json(path, type_name)
                        expected_type = ObjectType(type_name)
                        break
                    except FileNotFoundError:
                        continue
                
                if json_path is None:
                    logger.warning(f"No object JSON found in: {path}")
                    return None
        
        # Load JSON
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            # Compute and store hash for change detection
            file_hash = compute_file_hash(json_path)
            if file_hash:
                self.file_hashes[json_path.as_posix()] = file_hash
            
            # Also hash the legacy file if we're using the versioned one
            # This detects if someone edits the legacy file
            if is_versioned:
                legacy_name = get_object_json_filename(expected_type.value)
                legacy_path = path / legacy_name
                if legacy_path.exists():
                    legacy_hash = compute_file_hash(legacy_path)
                    if legacy_hash:
                        self.file_hashes[legacy_path.as_posix()] = legacy_hash
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load {json_path}: {e}")
            return None
        
        # If legacy file, check if upgrade is needed
        if not is_versioned and needs_upgrade(data):
            logger.info(f"Upgrading legacy schema in {json_path}")
            upgraded_data = upgrade_to_latest(data)
            
            # Write to versioned file (legacy file remains untouched)
            versioned_filename = get_versioned_object_json_filename(expected_type.value, "2.0.0")
            versioned_path = path / versioned_filename
            try:
                with open(versioned_path, "w") as f:
                    json.dump(upgraded_data, f, indent=2)
                logger.info(f"Created versioned file: {versioned_path}")
                data = upgraded_data
            except IOError as e:
                logger.warning(f"Failed to write versioned file {versioned_path}: {e}")
                # Continue with upgraded data in memory even if write failed
        
        # Get name and version
        name = get_object_name(data)
        version = get_object_version(data)
        
        if not name:
            logger.warning(f"No name in {json_path}")
            return None
        
        # Check if already resolved (can happen when object is both a root path
        # and a child of another object). Return existing to preserve parent chain.
        if name in self.objects:
            return self.objects[name]
        
        # Create resolved object
        resolved = ResolvedObject(
            path=path,
            object_type=expected_type,
            name=name,
            version=version,
            data=data,
        )
        
        # Parse dependencies
        # Schema 2.0.0: "dependent" dict with type keys: {"gems": ["org.o3de.gem.a>=1.0.0"]}
        # Legacy: "dependencies" flat list: ["GemA", "GemB"]
        dependent = data.get("dependent", {})
        if isinstance(dependent, dict):
            for dep_list in dependent.values():
                if isinstance(dep_list, list):
                    for dep in dep_list:
                        resolved.dependencies.append(ObjectNameVersion(dep))
        
        # Also check legacy format (flat list)
        legacy_deps = data.get("dependencies", [])
        if isinstance(legacy_deps, list):
            for dep in legacy_deps:
                if isinstance(dep, str):
                    resolved.dependencies.append(ObjectNameVersion(dep))
        
        # Store in appropriate collection
        self.objects[name] = resolved
        
        type_dict = {
            ObjectType.ENGINE: self.engines,
            ObjectType.PROJECT: self.projects,
            ObjectType.GEM: self.gems,
            ObjectType.TEMPLATE: self.templates,
            ObjectType.REPO: self.repos,
            ObjectType.OVERLAY: self.overlays,
        }.get(expected_type)
        
        if type_dict is not None:
            type_dict[name] = resolved
        
        # Resolve children
        # Schema 2.0.0: children is a dict with type keys, paths include JSON filename
        # e.g., {"gems": ["Gems/MyGem/gem.json"], "projects": ["MyProject/project.json"]}
        children = data.get("children", {})
        if isinstance(children, dict):
            for child_type_str, child_paths in children.items():
                if not isinstance(child_paths, list):
                    continue
                
                # Skip unknown object types (e.g., "restricted" from legacy O3DE)
                try:
                    child_type = ObjectType(child_type_str.rstrip("s"))
                except ValueError:
                    logger.debug(f"Skipping unknown object type: {child_type_str}")
                    continue
                
                for child_rel_path in child_paths:
                    # Schema 2.0.0 paths include JSON filename, extract directory
                    rel_path = Path(child_rel_path)
                    if rel_path.suffix == ".json":
                        # Path is to JSON file, use parent as object directory
                        child_path = path / rel_path.parent
                    else:
                        # Legacy path without JSON filename
                        child_path = path / child_rel_path
                    child_resolved = self._resolve_object(child_path, child_type)
                    if child_resolved:
                        child_resolved.parent = resolved
                        resolved.children.append(child_resolved)
        
        # Legacy format: external_subdirectories is a list of paths
        # These SHOULD be CMake-only directories (not O3DE objects), but people often
        # mistakenly put gem paths here. We try to detect actual O3DE objects.
        external_subdirs = data.get("external_subdirectories", [])
        if isinstance(external_subdirs, list):
            for child_rel_path in external_subdirs:
                child_path = path / child_rel_path
                if not child_path.exists():
                    continue
                
                # Try to detect O3DE object type from existing JSON
                detected_type = None
                for type_name in ["gem", "project", "engine", "template"]:
                    try:
                        find_object_json(child_path, type_name)
                        detected_type = ObjectType(type_name)
                        break
                    except FileNotFoundError:
                        continue
                
                if detected_type:
                    # It's an O3DE object (probably a gem mistakenly in external_subdirectories)
                    child_resolved = self._resolve_object(child_path, detected_type)
                    if child_resolved:
                        child_resolved.parent = resolved
                        resolved.children.append(child_resolved)
                else:
                    # True external subdirectory - just CMakeLists.txt, not an O3DE object
                    # Skip for object resolution (CMake will pick it up during build)
                    logger.debug(f"Skipping non-O3DE external subdirectory: {child_path}")
        
        return resolved
    
    def _remove_stale_paths(self, stale_paths: list[tuple[str, str]]) -> None:
        """
        Remove stale paths from the manifest file.
        
        Args:
            stale_paths: List of (path_str, obj_type) tuples to remove
        """
        if not stale_paths or not self.manifest_path.exists():
            return
        
        try:
            with open(self.manifest_path, "r") as f:
                manifest = json.load(f)
            
            local = manifest.get("local", {})
            modified = False
            
            for path_str, obj_type in stale_paths:
                type_list = local.get(obj_type, [])
                if path_str in type_list:
                    type_list.remove(path_str)
                    modified = True
                    logger.info(f"Removed stale {obj_type.rstrip('s')}: {path_str}")
            
            if modified:
                with open(self.manifest_path, "w") as f:
                    json.dump(manifest, f, indent=2)
                logger.info(f"Updated manifest: {self.manifest_path}")
        except Exception as e:
            logger.warning(f"Failed to remove stale paths from manifest: {e}")
    
    def _match_overlays(self) -> None:
        """Match overlays to their base objects."""
        for overlay in self.overlays.values():
            extends = overlay.data.get("extends", "")
            if not extends:
                continue
            
            # Parse version constraint from extends
            extends_spec = ObjectNameVersion(extends)
            
            # Find matching base object
            base = self.objects.get(extends_spec.name)
            if base:
                if extends_spec.matches(base.version):
                    base.overlays.append(overlay)
                    logger.debug(f"Matched overlay {overlay.name} -> {base.name}")
                else:
                    logger.warning(
                        f"Overlay {overlay.name} version mismatch: "
                        f"extends {extends_spec} but found {base.version}"
                    )
            else:
                logger.warning(f"Overlay {overlay.name} extends unknown object: {extends}")
    
    def get_dependencies_for(self, obj_name: str) -> list[ResolvedObject]:
        """Get all resolved dependencies for an object."""
        obj = self.objects.get(obj_name)
        if not obj:
            return []
        
        resolved_deps = []
        for dep_spec in obj.dependencies:
            # Find matching object
            for candidate in self.objects.values():
                if candidate.name == dep_spec.name:
                    if dep_spec.matches(candidate.version):
                        resolved_deps.append(candidate)
                        break
        
        return resolved_deps
    
    def get_objects_for_layout(
        self,
        root_name: str,
        include_overlays: bool = True,
    ) -> tuple[list[ResolvedObject], list[ResolvedObject]]:
        """
        Get all objects needed for a layout.
        
        Args:
            root_name: Name of root object (engine or project)
            include_overlays: Include matching overlays
        
        Returns:
            Tuple of (objects, overlays)
        """
        root = self.objects.get(root_name)
        if not root:
            raise ResolverError(f"Object not found: {root_name}")
        
        # Collect all dependencies recursively
        visited = set()
        objects = []
        
        def collect(obj: ResolvedObject):
            if obj.name in visited:
                return
            visited.add(obj.name)
            objects.append(obj)
            
            for dep in self.get_dependencies_for(obj.name):
                collect(dep)
            
            for child in obj.children:
                collect(child)
        
        collect(root)
        
        # Collect overlays
        overlays = []
        if include_overlays:
            for obj in objects:
                overlays.extend(obj.overlays)
            
            # Sort by precedence
            overlays.sort(key=lambda o: o.data.get("precedence", 0))
        
        return objects, overlays
    
    def save(self) -> Path:
        """
        Save resolved manifest to resolved_o3de_manifest.json.
        
        Computes and stores:
        - dependents: reverse dependencies (objects that depend on each object)
        - display_metadata: display_name, summary, icon_path from object data
        - git_info: remote_url and current branch for cloned repos
        - parent: reference to parent object that contains this one
        
        Returns:
            Path to saved file
        """
        # Use default data as-is; we do NOT convert restricteds_path to overlays_path
        # because restricted and overlay are different concepts
        default_data = dict(self.manifest_data.get("default", {}))
        
        # First pass: compute dependents by inverting dependencies
        dependents_map: dict[str, list[str]] = {}  # object_name -> list of names that depend on it
        for name, obj in self.objects.items():
            for dep in obj.dependencies:
                # Find matching object
                dep_name = dep.name
                if dep_name in self.objects:
                    if dep_name not in dependents_map:
                        dependents_map[dep_name] = []
                    if name not in dependents_map[dep_name]:
                        dependents_map[dep_name].append(name)
        
        resolved_data = {
            "$schema": "https://overlo3de.com/o3de-resolved-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "resolved_at": __import__("datetime").datetime.now().isoformat(),
            "manifest_path": self.manifest_path.as_posix(),
            
            # Defaults from manifest (normalized)
            "default": default_data,
            
            # File hashes for change detection
            "file_hashes": self.file_hashes,
            
            # All resolved objects with full paths
            "objects": {},
            
            # By-type lists for convenience
            "engines": [],
            "projects": [],
            "gems": [],
            "templates": [],
            "repos": [],
            "overlays": [],
        }
        
        for name, obj in self.objects.items():
            # Extract display metadata from object data
            # Schema 2.0.0: display_name/description are inside the type dict (e.g., gem.display_name)
            # Legacy: display_name/summary at root level
            display_metadata = {}
            
            type_key = obj.object_type.value  # "gem", "engine", etc.
            type_data = obj.data.get(type_key, {})
            
            # Try Schema 2.0.0 location first, then legacy
            display_name = type_data.get("display_name") or obj.data.get("display_name")
            description = type_data.get("description") or obj.data.get("summary")
            
            if display_name:
                display_metadata["display_name"] = display_name
            if description:
                display_metadata["summary"] = description
            
            # Icon: Schema 2.0.0 has icon.relative_path, legacy has icon_path
            icon_data = obj.data.get("icon", {})
            icon_path = icon_data.get("relative_path") if isinstance(icon_data, dict) else None
            if not icon_path:
                icon_path = obj.data.get("icon_path")
            if icon_path:
                display_metadata["icon_path"] = icon_path
            
            # Get git info for cloned repos
            git_info = {}
            remote_url = get_local_git_remote(str(obj.path))
            if remote_url:
                git_info["remote_url"] = remote_url
                branch = get_local_git_branch(str(obj.path))
                if branch:
                    git_info["branch"] = branch
            
            # Compute full ancestry chain (immediate parent to root)
            # Each entry has name and path for navigation
            parents = []
            current = obj.parent
            while current:
                parents.append({
                    "name": current.name,
                    "path": current.path.as_posix(),
                })
                current = current.parent
            
            # Extract releases (version names only for caching)
            releases_list = obj.data.get("releases", [])
            release_versions = []
            if releases_list and isinstance(releases_list, list):
                for release in releases_list:
                    if isinstance(release, dict):
                        version = release.get("name") or release.get("version")
                        if version:
                            release_versions.append(version)
            
            resolved_data["objects"][name] = {
                "path": obj.path.as_posix(),
                "type": obj.object_type.value,
                "version": obj.version,
                "children": [c.name for c in obj.children],
                "dependencies": [str(d) for d in obj.dependencies],
                "dependents": dependents_map.get(name, []),
                "overlays": [o.name for o in obj.overlays],
                "parent": obj.parent.name if obj.parent else None,
                "parents": parents,  # Full ancestry: [{name, path}, ...] from immediate parent to root
                "display_metadata": display_metadata if display_metadata else None,
                "git_info": git_info if git_info else None,
                "releases": release_versions if release_versions else None,
            }
            
            # Add to type list
            type_key = obj.object_type.value + "s"
            if type_key in resolved_data:
                resolved_data[type_key].append({
                    "name": name,
                    "path": obj.path.as_posix(),
                    "version": obj.version,
                })
        
        with open(self.resolved_path, "w") as f:
            json.dump(resolved_data, f, indent=2)
        
        logger.info(f"Saved resolved manifest: {self.resolved_path}")
        return self.resolved_path
    
    def load_resolved(self) -> dict:
        """Load existing resolved manifest."""
        if not self.resolved_path.exists():
            raise ResolverError("No resolved manifest. Run resolve() first.")
        
        with open(self.resolved_path, "r") as f:
            return json.load(f)


def check_files_changed(resolved_path: Optional[Path] = None) -> tuple[bool, list[str]]:
    """
    Check if any tracked files have changed since last resolution.
    
    Reads the file_hashes from the resolved manifest and compares against
    current file hashes.
    
    Args:
        resolved_path: Path to resolved manifest (default: ~/.o3de/resolved_o3de_manifest.json)
        
    Returns:
        Tuple of (has_changes, list_of_changed_files)
    """
    if resolved_path is None:
        resolved_path = get_resolved_manifest_path()
    
    if not resolved_path.exists():
        return True, ["resolved manifest not found"]
    
    try:
        with open(resolved_path, "r") as f:
            resolved_data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return True, ["failed to read resolved manifest"]
    
    stored_hashes = resolved_data.get("file_hashes", {})
    if not stored_hashes:
        return True, ["no hashes stored"]
    
    changed_files = []
    
    for file_path, stored_hash in stored_hashes.items():
        path = Path(file_path)
        if not path.exists():
            changed_files.append(f"deleted: {file_path}")
            continue
        
        current_hash = compute_file_hash(path)
        if current_hash != stored_hash:
            changed_files.append(file_path)
    
    return bool(changed_files), changed_files


def resolve_manifest(
    manifest_path: Optional[Path] = None,
    save: bool = True,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Resolver:
    """
    Convenience function to resolve the manifest.
    
    Args:
        manifest_path: Path to manifest (default: ~/.o3de/o3de_manifest.json)
        save: Whether to save resolved manifest
        progress_callback: Progress callback
    
    Returns:
        Resolver with resolved objects
    """
    resolver = Resolver(manifest_path)
    resolver.resolve(progress_callback)
    
    if save:
        resolver.save()
    
    return resolver


def load_resolved_manifest(
    force_refresh: bool = False,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> dict:
    """
    Load the resolved manifest, using cached version if files haven't changed.
    
    This is the recommended way for GUIs and tools to get resolved data - it
    avoids re-resolving when nothing has changed, dramatically improving
    startup time.
    
    The returned dict contains precomputed fields for each object:
    - display_metadata: {display_name, summary, icon_path}
    - git_info: {remote_url, branch}
    - parents: [{name, path}, ...] ancestry chain to root
    - dependents: reverse dependencies
    
    Args:
        force_refresh: If True, re-resolve even if files haven't changed
        progress_callback: Progress callback for resolution
        
    Returns:
        Dict with resolved manifest data including precomputed fields
    """
    resolved_path = get_resolved_manifest_path()
    
    # Check if we can use cached version
    if not force_refresh and resolved_path.exists():
        has_changes, changed_files = check_files_changed(resolved_path)
        if not has_changes:
            # Load from cache
            logger.info("Using cached resolved manifest (no file changes)")
            with open(resolved_path, "r") as f:
                return json.load(f)
        else:
            logger.info(f"Re-resolving due to {len(changed_files)} changed files")
    
    # Resolve fresh
    resolver = resolve_manifest(progress_callback=progress_callback)
    
    # Return the saved data
    with open(resolved_path, "r") as f:
        return json.load(f)
