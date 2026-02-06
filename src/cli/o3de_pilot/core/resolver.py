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

logger = logging.getLogger("o3de_pilot.resolver")


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
        
        # Load manifest
        with open(self.manifest_path, "r") as f:
            self.manifest_data = json.load(f)
        
        # Handle both Schema 2.0.0 (local.engines) and legacy (engines at root) formats
        local = self.manifest_data.get("local", {})
        
        # Collect all root paths to resolve
        root_paths = []
        for obj_type in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
            # Schema 2.0.0: local.engines, local.projects, etc.
            paths = local.get(obj_type, [])
            # Legacy: engines, projects, etc. at root level
            if not paths:
                paths = self.manifest_data.get(obj_type, []) or []
            for path_str in paths:
                root_paths.append((Path(path_str), obj_type))
        
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
            json_path = path
            is_versioned = '.2-0-0.' in path.name or '-2-0-0.' in path.name
            # Use parent directory as the object root
            path = path.parent
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
        
        # Create resolved object
        resolved = ResolvedObject(
            path=path,
            object_type=expected_type,
            name=name,
            version=version,
            data=data,
        )
        
        # Parse dependencies
        dependencies = data.get("dependencies", {})
        if isinstance(dependencies, dict):
            for dep_list in dependencies.values():
                if isinstance(dep_list, list):
                    for dep in dep_list:
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
                        resolved.children.append(child_resolved)
                else:
                    # True external subdirectory - just CMakeLists.txt, not an O3DE object
                    # Skip for object resolution (CMake will pick it up during build)
                    logger.debug(f"Skipping non-O3DE external subdirectory: {child_path}")
        
        return resolved
    
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
        
        Returns:
            Path to saved file
        """
        resolved_data = {
            "$schema": "https://overlo3de.com/o3de-resolved-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "resolved_at": __import__("datetime").datetime.now().isoformat(),
            "manifest_path": str(self.manifest_path),
            
            # Defaults from manifest
            "default": self.manifest_data.get("default", {}),
            
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
            resolved_data["objects"][name] = {
                "path": str(obj.path),
                "type": obj.object_type.value,
                "version": obj.version,
                "children": [c.name for c in obj.children],
                "dependencies": [str(d) for d in obj.dependencies],
                "overlays": [o.name for o in obj.overlays],
            }
            
            # Add to type list
            type_key = obj.object_type.value + "s"
            if type_key in resolved_data:
                resolved_data[type_key].append({
                    "name": name,
                    "path": str(obj.path),
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
