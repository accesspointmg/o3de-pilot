# O3DE Pilot - Workspace Engine
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Workspace Engine for O3DE.

A Workspace is a symlinked directory tree that represents a build configuration.
Instead of copying files, it creates symbolic links from source locations.

Workspace creation process:
1. Resolve all dependencies for the root object (engine or project)
2. Create target directory structure
3. Link files from each resolved object
4. Apply overlays in precedence order (overlay files replace base files)

Benefits:
- No file duplication
- Changes in source immediately reflected in workspace
- Multiple workspaces can share the same source files
- Overlays provide clean file-level customization
"""

from pathlib import Path
from typing import Optional, Callable
import os
import shutil
import logging

from .models import (
    O3DEObject, ObjectType, Overlay,
    get_object_type, get_object_name, get_object_version
)

logger = logging.getLogger("o3de_pilot.workspace")


class WorkspaceError(Exception):
    """Error during workspace creation."""
    pass


# Backward-compatible aliases
LayoutError = WorkspaceError


class Workspace:
    """
    Represents a symlinked build workspace.
    
    A workspace has:
    - root_path: Where the workspace is created
    - root_object: The engine or project being laid out
    - resolved_objects: All objects resolved as dependencies
    - overlays: Overlays to apply (in precedence order)
    """
    
    def __init__(
        self,
        root_path: Path,
        root_object_path: Path,
        root_object_type: ObjectType,
    ):
        self.root_path = Path(root_path)
        self.root_object_path = Path(root_object_path)
        self.root_object_type = root_object_type
        
        # Resolved objects: name -> path
        self.resolved_objects: dict[str, Path] = {}
        
        # Overlays to apply: list of (overlay_path, precedence)
        self.overlays: list[tuple[Path, int]] = []
        
        # Files that were linked: layout_path -> source_path
        self.linked_files: dict[Path, Path] = {}
        
        # Excluded patterns (gitignore style)
        self.exclude_patterns: list[str] = [
            ".git",
            ".git/**",
            "__pycache__",
            "**/__pycache__",
            "*.pyc",
            "build/**",
            "Cache/**",
            "*.log",
        ]
    
    def add_resolved_object(self, name: str, path: Path) -> None:
        """Add a resolved object to include in the layout."""
        self.resolved_objects[name] = Path(path)
    
    def add_overlay(self, path: Path, precedence: int = 0) -> None:
        """Add an overlay to apply during layout creation."""
        self.overlays.append((Path(path), precedence))
        # Sort by precedence (lower first, higher applied last = wins)
        self.overlays.sort(key=lambda x: x[1])
    
    def should_exclude(self, relative_path: Path) -> bool:
        """Check if a file should be excluded from layout."""
        path_str = str(relative_path).replace("\\", "/")
        
        for pattern in self.exclude_patterns:
            if self._matches_pattern(path_str, pattern):
                return True
        return False
    
    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """Simple pattern matching (supports * and **)."""
        import fnmatch
        
        # Handle ** patterns
        if "**" in pattern:
            # Convert ** to regex-like matching
            parts = pattern.split("**")
            if len(parts) == 2:
                prefix, suffix = parts
                if prefix and not path.startswith(prefix.rstrip("/")):
                    return False
                if suffix and not path.endswith(suffix.lstrip("/")):
                    return False
                return True
        
        return fnmatch.fnmatch(path, pattern)
    
    def create(
        self,
        clean: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None
    ) -> "Layout":
        """
        Create the workspace by linking files.
        
        Args:
            clean: If True, remove existing workspace first
            progress_callback: Optional callback(message, current, total)
        
        Returns:
            Self for chaining
        """
        if self.root_path.exists():
            if clean:
                logger.info(f"Cleaning existing workspace: {self.root_path}")
                shutil.rmtree(self.root_path)
            else:
                raise WorkspaceError(f"Workspace path already exists: {self.root_path}")
        
        # Create root directory
        self.root_path.mkdir(parents=True, exist_ok=True)
        
        # Calculate total files for progress
        total_files = 0
        for obj_name, obj_path in self.resolved_objects.items():
            total_files += sum(1 for _ in obj_path.rglob("*") if _.is_file())
        
        current = 0
        
        # Link files from each resolved object
        for obj_name, obj_path in self.resolved_objects.items():
            if progress_callback:
                progress_callback(f"Linking {obj_name}", current, total_files)
            
            current = self._link_object_files(obj_path, current, total_files, progress_callback)
        
        # Apply overlays in precedence order
        for overlay_path, precedence in self.overlays:
            if progress_callback:
                progress_callback(f"Applying overlay (precedence {precedence})", current, total_files)
            
            self._apply_overlay(overlay_path)
        
        if progress_callback:
            progress_callback("Complete", total_files, total_files)
        
        logger.info(f"Workspace created: {self.root_path} ({len(self.linked_files)} files)")
        return self
    
    def _link_object_files(
        self,
        source_path: Path,
        current: int,
        total: int,
        progress_callback: Optional[Callable] = None
    ) -> int:
        """Link all files from an object into the workspace."""
        for source_file in source_path.rglob("*"):
            if not source_file.is_file():
                continue
            
            relative = source_file.relative_to(source_path)
            
            if self.should_exclude(relative):
                continue
            
            target = self.root_path / relative
            
            self._create_link(source_file, target)
            
            current += 1
            if progress_callback and current % 100 == 0:
                progress_callback(f"Linking files", current, total)
        
        return current
    
    def _apply_overlay(self, overlay_path: Path) -> None:
        """
        Apply an overlay to the workspace.
        
        Files in the overlay replace matching files in the base layout.
        New files are added.
        """
        if not overlay_path.exists():
            logger.warning(f"Overlay path does not exist: {overlay_path}")
            return
        
        for overlay_file in overlay_path.rglob("*"):
            if not overlay_file.is_file():
                continue
            
            # Skip overlay.json itself
            if overlay_file.name == "overlay.json":
                continue
            
            relative = overlay_file.relative_to(overlay_path)
            
            if self.should_exclude(relative):
                continue
            
            target = self.root_path / relative
            
            # If file exists, it was from base - remove it
            if target.exists() or target.is_symlink():
                target.unlink()
                logger.debug(f"Overlay replacing: {relative}")
            
            self._create_link(overlay_file, target)
    
    def _create_link(self, source: Path, target: Path) -> None:
        """Create a symbolic link from target to source."""
        # Ensure parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Don't overwrite existing
        if target.exists() or target.is_symlink():
            return
        
        try:
            # Use relative symlinks when possible for portability
            try:
                rel_source = os.path.relpath(source, target.parent)
                target.symlink_to(rel_source)
            except ValueError:
                # Different drives on Windows - use absolute path
                target.symlink_to(source)
            
            self.linked_files[target] = source
            
        except OSError as e:
            if "privilege" in str(e).lower():
                # Windows without Developer Mode - use hard links for files
                logger.debug(f"Symlink failed, trying hard link: {target}")
                os.link(source, target)
                self.linked_files[target] = source
            else:
                raise WorkspaceError(f"Failed to create link {target} -> {source}: {e}")
    
    def update(self) -> None:
        """
        Update an existing workspace.
        
        Re-checks links and applies any new overlay changes.
        Does not remove files that were manually added to the workspace.
        """
        if not self.root_path.exists():
            raise WorkspaceError(f"Workspace does not exist: {self.root_path}")
        
        # Check for broken links
        broken = []
        for link_path, source_path in self.linked_files.items():
            if link_path.is_symlink() and not link_path.resolve().exists():
                broken.append(link_path)
        
        if broken:
            logger.warning(f"Found {len(broken)} broken links")
            for link in broken:
                link.unlink()
                del self.linked_files[link]
        
        # Re-apply overlays (they might have changed)
        for overlay_path, precedence in self.overlays:
            self._apply_overlay(overlay_path)
    
    def get_stats(self) -> dict:
        """Get workspace statistics."""
        return {
            "root_path": str(self.root_path),
            "root_object": str(self.root_object_path),
            "total_files": len(self.linked_files),
            "resolved_objects": len(self.resolved_objects),
            "overlays": len(self.overlays),
        }


def create_workspace(
    target_path: Path,
    root_object_path: Path,
    resolved_objects: dict[str, Path],
    overlays: list[tuple[Path, int]] = None,
    clean: bool = False,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Workspace:
    """
    Convenience function to create a workspace.
    
    Args:
        target_path: Where to create the workspace
        root_object_path: Path to the root engine or project
        resolved_objects: Dict of object_name -> object_path for all dependencies
        overlays: List of (overlay_path, precedence) tuples
        clean: If True, remove existing workspace first
        progress_callback: Optional progress callback
    
    Returns:
        Created Workspace object
    """
    # Determine root object type from its JSON
    root_json = root_object_path / "engine.json"
    if root_json.exists():
        root_type = ObjectType.ENGINE
    elif (root_object_path / "project.json").exists():
        root_type = ObjectType.PROJECT
    else:
        raise WorkspaceError(f"Cannot determine root object type at: {root_object_path}")
    
    ws = Workspace(target_path, root_object_path, root_type)
    
    # Always include the root object
    ws.add_resolved_object("_root_", root_object_path)
    
    # Add resolved dependencies
    for name, path in resolved_objects.items():
        ws.add_resolved_object(name, path)
    
    # Add overlays
    if overlays:
        for overlay_path, precedence in overlays:
            ws.add_overlay(overlay_path, precedence)
    
    return ws.create(clean=clean, progress_callback=progress_callback)


# Backward-compatible aliases
Layout = Workspace
create_layout = create_workspace
