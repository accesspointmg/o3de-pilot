# O3DE Pilot - Workspace Engine
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Workspace Engine for O3DE.

A Workspace is a structured directory tree that mirrors a standard O3DE
repository layout.  Instead of copying files, it creates **real directories**
with **symbolic links** to the original source files.

Layout::

    <workspace>/
    ├── workspace.json          ← metadata + file_owners
    ├── Engines/
    │   └── <engine_name>/      ← real dirs, symlinked files
    ├── Projects/
    │   └── <project_name>/
    ├── Gems/
    │   └── <gem_name>/
    ├── Templates/
    │   └── <template_name>/
    └── Overlays/
        └── <overlay_name>/

Process:
1.  User selects a root object (engine or project).
2.  The solver resolves the full transitive dependency graph.
3.  For every object in the solution the engine:
    a.  Determines its ObjectType → picks the top-level folder.
    b.  Creates *real* sub-directories mirroring the source tree.
    c.  Creates *symlinks* for every file pointing back to the source.
4.  Overlays are applied last — overlay files replace base symlinks and
    ownership transfers.
5.  ``file_owners`` records  ``workspace-relative POSIX path → object name``.
"""

from pathlib import Path
from typing import Optional, Callable
import os
import shutil
import logging

from .models import ObjectType

logger = logging.getLogger("o3de_pilot.workspace")


# ObjectType → top-level workspace folder name
_TYPE_FOLDERS: dict[ObjectType, str] = {
    ObjectType.ENGINE: "Engines",
    ObjectType.PROJECT: "Projects",
    ObjectType.GEM: "Gems",
    ObjectType.TEMPLATE: "Templates",
    ObjectType.OVERLAY: "Overlays",
}


class WorkspaceError(Exception):
    """Error during workspace creation."""
    pass


# Backward-compatible aliases
LayoutError = WorkspaceError


class Workspace:
    """
    Represents a structured symlinked workspace.

    A workspace has:
    - root_path: Where the workspace is created
    - root_object_path: The engine or project used as the root
    - root_object_type: ENGINE or PROJECT
    - resolved_objects: All objects to include (name → (path, type))
    - overlays: Overlays to apply (in precedence order)
    - file_owners: workspace-relative POSIX path → object name
    - linked_files: workspace-absolute path → source-absolute path
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

        # Resolved objects: name → (source_path, object_type)
        self.resolved_objects: dict[str, tuple[Path, ObjectType]] = {}

        # Overlays to apply: list of (overlay_path, precedence, extends_name)
        # extends_name is the base object name the overlay modifies (or None)
        self.overlays: list[tuple[Path, int, str | None]] = []

        # Files that were linked: workspace_abs_path → source_abs_path
        self.linked_files: dict[Path, Path] = {}

        # File ownership: workspace-relative POSIX path → object name
        self.file_owners: dict[str, str] = {}

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

    # -- public API ----------------------------------------------------------

    def add_resolved_object(
        self, name: str, path: Path, object_type: ObjectType,
    ) -> None:
        """Add a resolved object to include in the workspace."""
        self.resolved_objects[name] = (Path(path), object_type)

    def add_overlay(
        self, path: Path, precedence: int = 0, extends: str | None = None,
    ) -> None:
        """Add an overlay to apply during workspace creation.

        Args:
            path: Path to overlay source directory.
            precedence: Lower = applied first.
            extends: Base object name this overlay modifies.  When set,
                     overlay files also replace matching symlinks inside
                     the base object's workspace tree.
        """
        self.overlays.append((Path(path), precedence, extends))
        self.overlays.sort(key=lambda x: x[1])

    def create(
        self,
        clean: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> "Workspace":
        """Create the workspace directory tree with symlinked files.

        Returns self for chaining.
        """
        if self.root_path.exists():
            if clean:
                logger.info(f"Cleaning existing workspace: {self.root_path}")
                shutil.rmtree(self.root_path)
            else:
                raise WorkspaceError(
                    f"Workspace path already exists: {self.root_path}"
                )

        # Create root and top-level type folders
        self.root_path.mkdir(parents=True, exist_ok=True)
        for folder in _TYPE_FOLDERS.values():
            (self.root_path / folder).mkdir(exist_ok=True)

        # Count total files for progress
        total_files = 0
        for _name, (obj_path, _otype) in self.resolved_objects.items():
            total_files += sum(1 for f in obj_path.rglob("*") if f.is_file())
        current = 0

        # Link each resolved object into its type folder
        for obj_name, (obj_path, obj_type) in self.resolved_objects.items():
            if progress_callback:
                progress_callback(f"Linking {obj_name}", current, total_files)

            folder = _TYPE_FOLDERS.get(obj_type, "Gems")
            # Derive the short directory name from the object name
            short_name = _short_name(obj_name)
            dest_root = self.root_path / folder / short_name

            current = self._link_object_files(
                source_root=obj_path,
                dest_root=dest_root,
                owner_name=obj_name,
                current=current,
                total=total_files,
                progress_callback=progress_callback,
            )

        # Apply overlays in precedence order
        for overlay_path, precedence, extends_name in self.overlays:
            if progress_callback:
                progress_callback(
                    f"Applying overlay (precedence {precedence})",
                    current, total_files,
                )
            overlay_name = overlay_path.name
            dest_root = self.root_path / "Overlays" / overlay_name

            # Resolve the base object's workspace tree for merge
            base_dest_root: Path | None = None
            if extends_name and extends_name in self.resolved_objects:
                base_path, base_type = self.resolved_objects[extends_name]
                base_folder = _TYPE_FOLDERS.get(base_type, "Gems")
                base_short = _short_name(extends_name)
                base_dest_root = self.root_path / base_folder / base_short

            self._apply_overlay(
                overlay_path,
                dest_root=dest_root,
                owner_name=overlay_name,
                base_dest_root=base_dest_root,
            )

        if progress_callback:
            progress_callback("Complete", total_files, total_files)

        logger.info(
            f"Workspace created: {self.root_path} "
            f"({len(self.linked_files)} files)"
        )
        return self

    # -- internal helpers ----------------------------------------------------

    def _link_object_files(
        self,
        source_root: Path,
        dest_root: Path,
        owner_name: str,
        current: int = 0,
        total: int = 0,
        progress_callback: Optional[Callable] = None,
    ) -> int:
        """Mirror *source_root* into *dest_root*: real dirs, symlinked files."""
        for source_file in source_root.rglob("*"):
            if not source_file.is_file():
                continue
            relative = source_file.relative_to(source_root)
            if self.should_exclude(relative):
                continue

            target = dest_root / relative
            self._create_link(source_file, target)

            ws_rel = target.relative_to(self.root_path).as_posix()
            self.file_owners[ws_rel] = owner_name

            current += 1
            if progress_callback and current % 100 == 0:
                progress_callback("Linking files", current, total)

        return current

    def _apply_overlay(
        self,
        overlay_path: Path,
        dest_root: Path,
        owner_name: str,
        base_dest_root: Path | None = None,
    ) -> None:
        """Apply an overlay — replaces matching files, adds new ones.

        Files are always linked into the ``Overlays/<name>/`` audit tree.
        When *base_dest_root* is given, matching files inside the base
        object's workspace tree are replaced with symlinks to the overlay
        source, and ownership is transferred.
        """
        if not overlay_path.exists():
            logger.warning(f"Overlay path does not exist: {overlay_path}")
            return

        for overlay_file in overlay_path.rglob("*"):
            if not overlay_file.is_file():
                continue
            if overlay_file.name == "overlay.json":
                continue
            relative = overlay_file.relative_to(overlay_path)
            if self.should_exclude(relative):
                continue

            # 1. Link into Overlays/ audit tree
            target = dest_root / relative
            if target.exists() or target.is_symlink():
                target.unlink()
                logger.debug(f"Overlay replacing: {relative}")
            self._create_link(overlay_file, target)
            ws_rel = target.relative_to(self.root_path).as_posix()
            self.file_owners[ws_rel] = owner_name

            # 2. Merge into base object tree (replace matching symlink)
            if base_dest_root is not None:
                base_target = base_dest_root / relative
                if base_target.exists() or base_target.is_symlink():
                    base_target.unlink()
                    logger.debug(f"Overlay merging into base: {relative}")
                else:
                    base_target.parent.mkdir(parents=True, exist_ok=True)
                self._force_link(overlay_file, base_target)
                base_ws_rel = base_target.relative_to(
                    self.root_path
                ).as_posix()
                self.file_owners[base_ws_rel] = owner_name

    def _create_link(self, source: Path, target: Path) -> None:
        """Create a symbolic link from *target* → *source*."""
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() or target.is_symlink():
            return

        try:
            try:
                rel_source = os.path.relpath(source, target.parent)
                target.symlink_to(rel_source)
            except ValueError:
                # Different drives on Windows
                target.symlink_to(source)
            self.linked_files[target] = source
        except OSError as e:
            if "privilege" in str(e).lower():
                logger.debug(f"Symlink failed, trying hard link: {target}")
                os.link(source, target)
                self.linked_files[target] = source
            else:
                raise WorkspaceError(
                    f"Failed to create link {target} -> {source}: {e}"
                )

    def _force_link(self, source: Path, target: Path) -> None:
        """Create a symbolic link, removing any existing file first."""
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        try:
            try:
                rel_source = os.path.relpath(source, target.parent)
                target.symlink_to(rel_source)
            except ValueError:
                target.symlink_to(source)
            self.linked_files[target] = source
        except OSError as e:
            if "privilege" in str(e).lower():
                logger.debug(f"Symlink failed, trying hard link: {target}")
                os.link(source, target)
                self.linked_files[target] = source
            else:
                raise WorkspaceError(
                    f"Failed to create link {target} -> {source}: {e}"
                )

    def should_exclude(self, relative_path: Path) -> bool:
        """Check if a file should be excluded from workspace."""
        path_str = str(relative_path).replace("\\", "/")
        for pattern in self.exclude_patterns:
            if self._matches_pattern(path_str, pattern):
                return True
        return False

    def _matches_pattern(self, path: str, pattern: str) -> bool:
        """Simple pattern matching (supports * and **)."""
        import fnmatch
        if "**" in pattern:
            parts = pattern.split("**")
            if len(parts) == 2:
                prefix, suffix = parts
                if prefix and not path.startswith(prefix.rstrip("/")):
                    return False
                if suffix and not path.endswith(suffix.lstrip("/")):
                    return False
                return True
        return fnmatch.fnmatch(path, pattern)

    def update(self) -> None:
        """Re-check links and re-apply overlays."""
        if not self.root_path.exists():
            raise WorkspaceError(
                f"Workspace does not exist: {self.root_path}"
            )
        broken = []
        for link_path, source_path in self.linked_files.items():
            if link_path.is_symlink() and not link_path.resolve().exists():
                broken.append(link_path)
        if broken:
            logger.warning(f"Found {len(broken)} broken links")
            for link in broken:
                link.unlink()
                del self.linked_files[link]
        for overlay_path, _precedence, extends_name in self.overlays:
            overlay_name = overlay_path.name
            dest_root = self.root_path / "Overlays" / overlay_name

            base_dest_root: Path | None = None
            if extends_name and extends_name in self.resolved_objects:
                base_path, base_type = self.resolved_objects[extends_name]
                base_folder = _TYPE_FOLDERS.get(base_type, "Gems")
                base_short = _short_name(extends_name)
                base_dest_root = self.root_path / base_folder / base_short

            self._apply_overlay(
                overlay_path, dest_root, overlay_name,
                base_dest_root=base_dest_root,
            )

    def get_stats(self) -> dict:
        """Get workspace statistics."""
        return {
            "root_path": str(self.root_path),
            "root_object": str(self.root_object_path),
            "total_files": len(self.linked_files),
            "resolved_objects": len(self.resolved_objects),
            "overlays": len(self.overlays),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _short_name(object_name: str) -> str:
    """Derive a short directory name from a reverse-domain object name.

    ``org.o3de.engine.o3de`` → ``o3de``
    ``com.example.gem.atom``  → ``atom``
    Plain names pass through unchanged.
    """
    if "." in object_name:
        return object_name.rsplit(".", 1)[-1]
    return object_name


def detect_root_type(path: Path) -> ObjectType:
    """Detect the object type of a root directory.

    Checks Schema 2.0 sidecars first, then falls back to legacy JSON files.

    Raises:
        WorkspaceError: if no engine/project JSON can be found.
    """
    # Schema 2.0 sidecars (preferred)
    if (path / "engine.2-0-0.json").exists():
        return ObjectType.ENGINE
    if (path / "project.2-0-0.json").exists():
        return ObjectType.PROJECT
    # Legacy Schema 1.0
    if (path / "engine.json").exists():
        return ObjectType.ENGINE
    if (path / "project.json").exists():
        return ObjectType.PROJECT
    raise WorkspaceError(
        f"Cannot determine root object type at: {path}"
    )


def create_workspace(
    target_path: Path,
    root_object_path: Path,
    resolved_objects: dict[str, tuple[Path, ObjectType]],
    overlays: list[tuple[Path, int, str | None]] | list[tuple[Path, int]] | None = None,
    clean: bool = False,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Workspace:
    """Convenience function to create a workspace.

    Args:
        target_path: Where to create the workspace.
        root_object_path: Path to the root engine or project.
        resolved_objects: name → (path, ObjectType) for every dependency.
        overlays: (overlay_path, precedence[, extends_name]) tuples.
        clean: Remove existing workspace first.
        progress_callback: Optional progress callback.

    Returns:
        Created Workspace object.
    """
    root_type = detect_root_type(root_object_path)

    ws = Workspace(target_path, root_object_path, root_type)

    # Determine a name for the root object
    root_name = root_object_path.name
    ws.add_resolved_object(root_name, root_object_path, root_type)

    for name, (path, obj_type) in resolved_objects.items():
        ws.add_resolved_object(name, path, obj_type)

    if overlays:
        for entry in overlays:
            if len(entry) == 3:
                overlay_path, precedence, extends = entry
            else:
                overlay_path, precedence = entry  # type: ignore[misc]
                extends = None
            ws.add_overlay(overlay_path, precedence, extends=extends)

    return ws.create(clean=clean, progress_callback=progress_callback)


# Backward-compatible aliases
Layout = Workspace
create_layout = create_workspace
