# O3DE Pilot - Object Models
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Pydantic models for O3DE objects (Schema 2.0.0).

Object types:
- Engine: The O3DE engine or a fork
- Project: A game or application project
- Gem: A modular feature/asset package
- Template: Scaffolding for creating new objects
- Repo: A registry of available objects
- Overlay: File-level overlay on another object

Note: Legacy "Restricted" objects have no upgrade path to 2.0.0.
Overlay is a new concept in 2.0.0, not a replacement for Restricted.

Each object has a JSON file in its root (e.g. gem.json, engine.json).
Objects can have children (sub-objects) referenced by relative path.
Objects can have dependencies on other objects with version constraints.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional, Literal, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from enum import Enum
import re


# Schema version pattern
SCHEMA_VERSION = "2.0.0"
SCHEMA_BASE_URL = "https://canonical.o3de.org"


class ObjectType(str, Enum):
    """O3DE object types."""
    ENGINE = "engine"
    PROJECT = "project"
    GEM = "gem"
    TEMPLATE = "template"
    REPO = "repo"
    OVERLAY = "overlay"
    MANIFEST = "manifest"


class GemType(str, Enum):
    """Gem content type."""
    CODE = "code"
    ASSET = "asset"


class EngineType(str, Enum):
    """Engine type."""
    FULL = "full"
    SLIM = "slim"


# Reverse domain name pattern: org.o3de.gem.myname
OBJECT_NAME_PATTERN = re.compile(r"^(?=.{5,63}$)([a-z]+)\.[a-z0-9]+(\.[a-z0-9]+)+$")

# Version pattern: major.minor.patch
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

# Version specifier pattern: name==version or name>=version<=version
VERSION_SPEC_PATTERN = re.compile(
    r"^([a-z_]+)\.[a-z0-9_]+(\.[a-z0-9_]+){1,63}"
    r"((==([0-9]+\.[0-9]+\.[0-9]+))|"
    r"(((>=|>)?([0-9]+\.[0-9]+\.[0-9]+))?((<=|<)([0-9]+\.[0-9]+\.[0-9]+))?))$"
)


class Origin(BaseModel):
    """Object origin/ownership information."""
    name: str = Field(default="", description="Creator/maintainer name")
    url: Optional[str] = Field(default=None, description="Creator website URL")
    email: Optional[str] = Field(default=None, description="Contact email")


class License(BaseModel):
    """License information."""
    name: str = Field(description="License name (e.g., 'Apache-2.0')")
    url: Optional[str] = Field(default=None, description="License text URL")


class Icon(BaseModel):
    """Icon for display in UI."""
    relative_path: Optional[str] = Field(default=None, description="Path relative to object root")
    uri: Optional[str] = Field(default=None, description="Remote icon URL")


class Documentation(BaseModel):
    """Documentation reference."""
    relative_path: Optional[str] = Field(default=None, description="Path relative to object root")
    uri: Optional[str] = Field(default=None, description="Remote documentation URL")


class SourceControl(BaseModel):
    """Source control information for cloning."""
    uri: str = Field(description="Git clone URL")
    branch: Optional[str] = Field(default=None, description="Default branch")
    tag: Optional[str] = Field(default=None, description="Specific tag")
    commit: Optional[str] = Field(default=None, description="Specific commit SHA")


class Deprecated(BaseModel):
    """Marks an object version as deprecated."""
    message: str = Field(description="Human-readable deprecation reason")
    replacement: Optional[str] = Field(default=None, description="Replacement object name with version constraint")


class Hooks(BaseModel):
    """Optional scripts that run at key lifecycle points."""
    post_install: Optional[str] = Field(default=None, description="Script to run after install (relative path)")
    pre_build: Optional[str] = Field(default=None, description="Script to run before build (relative path)")


class Download(BaseModel):
    """Download information for release archives."""
    source: Optional[str] = Field(default=None, description="Source code archive URL")
    lfs: Optional[str] = Field(default=None, description="LFS/assets archive URL")
    relative_path: Optional[str] = Field(default=None, description="Relative path to object root within archive")
    source_sha256: Optional[str] = Field(default=None, description="SHA-256 hash of source archive")
    lfs_sha256: Optional[str] = Field(default=None, description="SHA-256 hash of LFS archive")


class Binary(BaseModel):
    """Pre-built binary download option."""
    platform: str = Field(description="Target platform (e.g., 'Windows 11 AMD64')")
    binary: str = Field(description="Binary archive URL")
    sha256: Optional[str] = Field(default=None, description="SHA-256 hash of binary archive")


class Release(BaseModel):
    """A specific release."""
    name: str = Field(description="Release name (date, codename, hash, etc.)")
    downloads: list[Download] = Field(default_factory=list, description="Download archives")
    binaries: list[Binary] = Field(default_factory=list, description="Pre-built binaries")
    source_controls: list[SourceControl] = Field(default_factory=list, description="Source control options")


class Children(BaseModel):
    """Child objects embedded within this object (relative paths only)."""
    engines: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    gems: list[str] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    overlays: list[str] = Field(default_factory=list)


class Dependencies(BaseModel):
    """Dependencies on other objects with optional version constraints.
    
    Matches the schema 2.0.0 objectNameAndVersionLists definition.
    Each list contains object names with optional version constraints.
    """
    engines: list[str] = Field(default_factory=list, description="Engine dependencies")
    projects: list[str] = Field(default_factory=list, description="Project dependencies")
    gems: list[str] = Field(default_factory=list, description="Gem dependencies")
    templates: list[str] = Field(default_factory=list, description="Template dependencies")
    repos: list[str] = Field(default_factory=list, description="Repo dependencies")
    overlays: list[str] = Field(default_factory=list, description="Overlay dependencies")
    manifests: list[str] = Field(default_factory=list, description="Manifest dependencies")


class Remote(BaseModel):
    """Remote object references (URLs to object JSON files)."""
    engines: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    gems: list[str] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    overlays: list[str] = Field(default_factory=list)


class BaseO3DEObject(BaseModel):
    """Base class for all O3DE objects."""
    model_config = ConfigDict(
        populate_by_name=True,
        extra="allow",  # Allow extra fields for forward compatibility
    )
    
    schema_: str = Field(alias="$schema", default="")
    schema_version: str = Field(alias="$schemaVersion", default=SCHEMA_VERSION)
    
    # Path to this object on disk (not persisted, set at load time)
    _path: Optional[Path] = None


class EngineHeader(BaseModel):
    """Engine object header (the 'engine' property in engine.json)."""
    name: str = Field(description="Reverse domain name: org.o3de.engine.o3de")
    version: str = Field(default="0.0.0")
    display_name: str = Field(default="")
    description: str = Field(default="")
    type: EngineType = Field(default=EngineType.FULL)
    id: str = Field(default="")
    copyright_year: Optional[int] = None
    copyright_text: str = Field(default="")


class Engine(BaseO3DEObject):
    """O3DE Engine object."""
    engine: EngineHeader
    origin: Optional[Origin] = None
    licenses: list[License] = Field(default_factory=list)
    icon: Optional[Icon] = None
    documentation: Optional[Documentation] = None
    canonical_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    requirements: str = Field(default="")
    children: Children = Field(default_factory=Children)
    dependencies: Dependencies = Field(default_factory=Dependencies)
    optional_dependent: Dependencies = Field(default_factory=Dependencies)
    peer_dependent: Dependencies = Field(default_factory=Dependencies)
    deprecated: Optional[Deprecated] = None
    hooks: Optional[Hooks] = None
    source_control: Optional[SourceControl] = None
    download: Optional[Download] = None
    releases: list[Release] = Field(default_factory=list)
    remote: Remote = Field(default_factory=Remote)
    
    # Engine-specific
    api_versions: dict[str, str] = Field(default_factory=dict)
    O3DEVersion: str = Field(default="")
    O3DEBuildNumber: str = Field(default="")


class ProjectHeader(BaseModel):
    """Project object header."""
    name: str = Field(description="Reverse domain name: org.o3de.project.myproject")
    version: str = Field(default="0.0.0")
    display_name: str = Field(default="")
    description: str = Field(default="")
    id: str = Field(default="")
    product_name: str = Field(default="")
    executable_name: str = Field(default="")


class Project(BaseO3DEObject):
    """O3DE Project object."""
    project: ProjectHeader
    engine: Optional[str] = Field(default=None, description="Engine dependency with version")
    origin: Optional[Origin] = None
    licenses: list[License] = Field(default_factory=list)
    icon: Optional[Icon] = None
    documentation: Optional[Documentation] = None
    canonical_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    requirements: str = Field(default="")
    children: Children = Field(default_factory=Children)
    dependencies: Dependencies = Field(default_factory=Dependencies)
    optional_dependent: Dependencies = Field(default_factory=Dependencies)
    peer_dependent: Dependencies = Field(default_factory=Dependencies)
    deprecated: Optional[Deprecated] = None
    hooks: Optional[Hooks] = None
    source_control: Optional[SourceControl] = None
    download: Optional[Download] = None
    releases: list[Release] = Field(default_factory=list)


class GemHeader(BaseModel):
    """Gem object header."""
    name: str = Field(description="Reverse domain name: org.o3de.gem.mygem")
    version: str = Field(default="0.0.0")
    display_name: str = Field(default="")
    description: str = Field(default="")
    type: GemType = Field(default=GemType.CODE)


class Gem(BaseO3DEObject):
    """O3DE Gem object."""
    gem: GemHeader
    origin: Optional[Origin] = None
    licenses: list[License] = Field(default_factory=list)
    icon: Optional[Icon] = None
    documentation: Optional[Documentation] = None
    canonical_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    requirements: str = Field(default="")
    children: Children = Field(default_factory=Children)
    dependencies: Dependencies = Field(default_factory=Dependencies)
    optional_dependent: Dependencies = Field(default_factory=Dependencies)
    peer_dependent: Dependencies = Field(default_factory=Dependencies)
    compatibilities: Dependencies = Field(default_factory=Dependencies)
    incompatibilities: Dependencies = Field(default_factory=Dependencies)
    deprecated: Optional[Deprecated] = None
    hooks: Optional[Hooks] = None
    source_control: Optional[SourceControl] = None
    download: Optional[Download] = None
    releases: list[Release] = Field(default_factory=list)


class TemplateHeader(BaseModel):
    """Template object header."""
    name: str = Field(description="Reverse domain name: org.o3de.template.mytemplate")
    version: str = Field(default="0.0.0")
    display_name: str = Field(default="")
    description: str = Field(default="")
    template_type: str = Field(default="", description="Type of object this creates: engine, project, gem")


class Template(BaseO3DEObject):
    """O3DE Template object."""
    template: TemplateHeader
    origin: Optional[Origin] = None
    licenses: list[License] = Field(default_factory=list)
    icon: Optional[Icon] = None
    documentation: Optional[Documentation] = None
    canonical_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    requirements: str = Field(default="")
    children: Children = Field(default_factory=Children)
    dependencies: Dependencies = Field(default_factory=Dependencies)
    optional_dependent: Dependencies = Field(default_factory=Dependencies)
    peer_dependent: Dependencies = Field(default_factory=Dependencies)
    deprecated: Optional[Deprecated] = None
    hooks: Optional[Hooks] = None
    source_control: Optional[SourceControl] = None
    download: Optional[Download] = None
    releases: list[Release] = Field(default_factory=list)
    
    # Template-specific
    copy_files: list[dict] = Field(default_factory=list, alias="copyFiles")
    create_directories: list[str] = Field(default_factory=list, alias="createDirectories")


class RepoHeader(BaseModel):
    """Repo object header."""
    name: str = Field(description="Reverse domain name: org.o3de.repo.community")
    version: str = Field(default="0.0.0")
    display_name: str = Field(default="")
    description: str = Field(default="")


class Repo(BaseO3DEObject):
    """O3DE Repo object (registry of objects)."""
    repo: RepoHeader
    origin: Optional[Origin] = None
    icon: Optional[Icon] = None
    documentation: Optional[Documentation] = None
    canonical_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    
    deprecated: Optional[Deprecated] = None
    hooks: Optional[Hooks] = None
    
    # Repos primarily contain remote references
    remote: Remote = Field(default_factory=Remote)


class OverlayHeader(BaseModel):
    """Overlay object header."""
    name: str = Field(description="Reverse domain name: org.o3de.overlay.console")
    version: str = Field(default="0.0.0")
    display_name: str = Field(default="")
    description: str = Field(default="")


class Overlay(BaseO3DEObject):
    """
    O3DE Overlay object.
    
    An overlay applies file-level modifications to a base object.
    Files in the overlay with the same path as the base replace them.
    New files are added.
    
    During layout creation, overlays are applied after linking base files.
    """
    overlay: OverlayHeader
    
    # What object(s) this overlay extends
    extends: str = Field(description="Object name this extends: org.o3de.engine.o3de")
    extends_version: Optional[str] = Field(default=None, description="Version constraint")
    
    # Priority when multiple overlays apply (higher = applied later)
    precedence: int = Field(default=0)
    
    origin: Optional[Origin] = None
    licenses: list[License] = Field(default_factory=list)
    icon: Optional[Icon] = None
    documentation: Optional[Documentation] = None
    canonical_tags: list[str] = Field(default_factory=list)
    user_tags: list[str] = Field(default_factory=list)
    platforms: list[str] = Field(default_factory=list)
    requirements: str = Field(default="")
    deprecated: Optional[Deprecated] = None
    hooks: Optional[Hooks] = None
    source_control: Optional[SourceControl] = None
    download: Optional[Download] = None
    releases: list[Release] = Field(default_factory=list)


class WorkspaceHeader(BaseModel):
    """Workspace object header."""
    name: str = Field(description="Human-readable workspace name")
    version: str = Field(default="0.0.0")
    display_name: str = Field(default="")
    description: str = Field(default="")


class ResolvedCandidate(BaseModel):
    """A resolved dependency candidate stored in workspace metadata."""
    name: str = Field(description="Object name (reverse domain)")
    version: str = Field(default="0.0.0", description="Resolved version")
    object_type: str = Field(description="Object type (engine, project, gem, etc.)")
    status: str = Field(default="local", description="local, remote, or unknown")
    path: Optional[str] = Field(default=None, description="Local path if available")


class WorkspaceMeta(BaseO3DEObject):
    """O3DE Workspace metadata.

    A workspace is a local build artifact — a directory of symlinks
    assembled from source objects and overlays.  Not an ObjectType;
    kept separate as a local-only construct.
    """
    workspace: WorkspaceHeader
    created: str = Field(description="ISO 8601 creation timestamp")
    root_object: Optional[str] = Field(default=None, description="Root object path")
    root_type: Optional[str] = Field(default=None, description="Root object type")
    sources: list[str] = Field(default_factory=list, description="Source object paths")
    overlays: list[str] = Field(default_factory=list, description="Overlay paths applied")
    file_owners: dict[str, str] = Field(
        default_factory=dict,
        description="Relative POSIX path -> owning object name",
    )
    resolved_candidates: list[ResolvedCandidate] = Field(
        default_factory=list,
        description="Full dependency solve result for reproducible rebuilds",
    )


class ManifestHeader(BaseModel):
    """Manifest header."""
    name: str = Field(description="Manifest name: me.home.username.manifest")


class ManifestDefaults(BaseModel):
    """Default paths for object storage."""
    engines_path: str
    projects_path: str
    gems_path: str
    templates_path: str
    repos_path: str
    overlays_path: str
    third_party_path: str


class LocalObjects(BaseModel):
    """Local object paths (full paths to object roots)."""
    engines: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    gems: list[str] = Field(default_factory=list)
    templates: list[str] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)
    overlays: list[str] = Field(default_factory=list)


class Manifest(BaseO3DEObject):
    """O3DE Manifest (user's registry of local/remote objects)."""
    o3de_manifest: ManifestHeader
    country: dict = Field(default_factory=lambda: {"code": "US"})
    default: ManifestDefaults
    local: LocalObjects = Field(default_factory=LocalObjects)
    remote: Remote = Field(default_factory=Remote)


# Type alias for any O3DE object
O3DEObject = Engine | Project | Gem | Template | Repo | Overlay | Manifest


def get_object_type(obj: O3DEObject | dict) -> ObjectType:
    """Determine object type from object or dict.
    
    Handles both legacy (schema 0/1.0) and 2.0.0 formats.
    """
    if isinstance(obj, Engine):
        return ObjectType.ENGINE
    elif isinstance(obj, Project):
        return ObjectType.PROJECT
    elif isinstance(obj, Gem):
        return ObjectType.GEM
    elif isinstance(obj, Template):
        return ObjectType.TEMPLATE
    elif isinstance(obj, Repo):
        return ObjectType.REPO
    elif isinstance(obj, Overlay):
        return ObjectType.OVERLAY
    elif isinstance(obj, Manifest):
        return ObjectType.MANIFEST
    elif isinstance(obj, dict):
        # Schema 2.0.0 format: has "engine", "project", etc. as top-level key
        if "engine" in obj:
            return ObjectType.ENGINE
        elif "project" in obj:
            return ObjectType.PROJECT
        elif "gem" in obj:
            return ObjectType.GEM
        elif "template" in obj:
            return ObjectType.TEMPLATE
        elif "repo" in obj:
            return ObjectType.REPO
        elif "overlay" in obj:
            return ObjectType.OVERLAY
        elif "o3de_manifest" in obj:
            return ObjectType.MANIFEST
        
        # Legacy format: has "engine_name", "project_name", etc.
        if "engine_name" in obj:
            return ObjectType.ENGINE
        elif "project_name" in obj:
            return ObjectType.PROJECT
        elif "gem_name" in obj:
            return ObjectType.GEM
        elif "template_name" in obj:
            return ObjectType.TEMPLATE
        elif "repo_name" in obj or "repo_uri" in obj:
            return ObjectType.REPO
        
        # Guess from origin.type if present
        origin = obj.get("origin", {})
        if isinstance(origin, dict):
            origin_type = origin.get("type", "")
            if origin_type in ["engine", "project", "gem", "template", "repo", "overlay"]:
                return ObjectType(origin_type)
        
        raise ValueError(f"Cannot determine object type from dict keys: {list(obj.keys())[:10]}")
    else:
        raise ValueError(f"Unknown object type: {type(obj)}")


def get_object_name(obj: O3DEObject | dict) -> str:
    """Get the canonical name from an object.
    
    Handles both legacy and 2.0.0 formats.
    """
    if isinstance(obj, dict):
        # Try 2.0.0 format first: engine.name, project.name, etc.
        for key in ["engine", "project", "gem", "template", "repo", "overlay"]:
            if key in obj and isinstance(obj[key], dict):
                return obj[key].get("name", "")
        
        # Legacy format: engine_name, project_name, etc.
        for key in ["engine_name", "project_name", "gem_name", "template_name", "repo_name"]:
            if key in obj:
                return obj[key]
        
        # Origin-based (schema 1.0)
        origin = obj.get("origin", {})
        if isinstance(origin, dict) and "name" in origin:
            return origin["name"]
        
        return ""
    
    # Pydantic model
    obj_type = get_object_type(obj)
    if obj_type == ObjectType.ENGINE:
        return obj.engine.name
    elif obj_type == ObjectType.PROJECT:
        return obj.project.name
    elif obj_type == ObjectType.GEM:
        return obj.gem.name
    elif obj_type == ObjectType.TEMPLATE:
        return obj.template.name
    elif obj_type == ObjectType.REPO:
        return obj.repo.name
    elif obj_type == ObjectType.OVERLAY:
        return obj.overlay.name
    elif obj_type == ObjectType.MANIFEST:
        return obj.o3de_manifest.name
    
    return ""


def get_object_version(obj: O3DEObject | dict) -> str:
    """Get the version from an object.
    
    Handles both legacy and 2.0.0 formats.
    """
    if isinstance(obj, dict):
        # Try 2.0.0 format first: engine.version, project.version, etc.
        for key in ["engine", "project", "gem", "template", "repo", "overlay"]:
            if key in obj and isinstance(obj[key], dict):
                return obj[key].get("version", "0.0.0")
        
        # Legacy format: version at top level
        if "version" in obj:
            return obj["version"]
        
        # Origin-based (schema 1.0)
        origin = obj.get("origin", {})
        if isinstance(origin, dict) and "version" in origin:
            return origin["version"]
        
        return "0.0.0"
    
    # Pydantic model
    obj_type = get_object_type(obj)
    if obj_type == ObjectType.ENGINE:
        return obj.engine.version
    elif obj_type == ObjectType.PROJECT:
        return obj.project.version
    elif obj_type == ObjectType.GEM:
        return obj.gem.version
    elif obj_type == ObjectType.TEMPLATE:
        return obj.template.version
    elif obj_type == ObjectType.REPO:
        return obj.repo.version
    elif obj_type == ObjectType.OVERLAY:
        return obj.overlay.version
    
    return "0.0.0"
