# O3DE Pilot CLI - Core Package
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Core business logic for O3DE Pilot.

Modules:
    paths - User directory management (~/.o3de, ~/O3DE)
    models - Pydantic models for O3DE objects (Schema 2.0.0)
    layout - Layout engine for symlinked build directories
    store - Remote object fetching, caching, search
    resolver - Manifest resolution and dependency handling
    upgrade - Schema migration (0 → 1.0 → 2.0.0)
"""

from .paths import (
    get_dot_o3de_path,
    get_o3de_path,
    get_manifest_path,
    get_resolved_manifest_path,
    get_cache_path,
    get_default_layouts_path,
    get_default_path_for_type,
    get_default_gems_path,
    initialize_user_directories,
    to_posix_path,
)

from .models import (
    ObjectType,
    O3DEObject,
    Origin,
    Children,
    Dependencies,
    Deprecated,
    Hooks,
    Download,
    Binary,
    Release,
    Engine,
    Project,
    Gem,
    Template,
    Repo,
    Overlay,
    Manifest,
    get_object_type,
    get_object_name,
    get_object_version,
)

from .layout import (
    Layout,
    create_layout,
)

from .store import (
    Cache,
    RemoteObject,
    Store,
    StoreError,
    IntegrityError,
    compute_sha256,
    verify_integrity,
)

from .resolver import (
    Resolver,
    ResolvedObject,
    ObjectNameVersion,
    DependencyConflict,
    resolve_manifest,
    check_files_changed,
)

from .upgrade import (
    get_schema_version,
    needs_upgrade,
    upgrade_to_latest,
    upgrade_file,
    upgrade_directory,
)

from .hooks import (
    HooksEngine,
    HookError,
)

__all__ = [
    # paths
    "get_dot_o3de_path",
    "get_o3de_path",
    "get_manifest_path",
    "get_resolved_manifest_path",
    "get_cache_path",
    "get_default_layouts_path",
    "initialize_user_directories",
    "to_posix_path",
    # models
    "ObjectType",
    "O3DEObject",
    "Origin",
    "Children",
    "Dependencies",
    "Deprecated",
    "Hooks",
    "Download",
    "Binary",
    "Release",
    "Engine",
    "Project",
    "Gem",
    "Template",
    "Repo",
    "Overlay",
    "Manifest",
    "get_object_type",
    "get_object_name",
    "get_object_version",
    # layout
    "Layout",
    "create_layout",
    # store
    "Cache",
    "RemoteObject",
    "Store",
    # resolver
    "Resolver",
    "ResolvedObject",
    "ObjectNameVersion",
    "resolve_manifest",
    "check_files_changed",
    # upgrade
    "get_schema_version",
    "needs_upgrade",
    "upgrade_to_latest",
    "upgrade_file",
    "upgrade_directory",
    # hooks
    "HooksEngine",
    "HookError",
]
