# O3DE Pilot GUI - Object Info
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Data class for object information displayed in the catalog.
This is analogous to GemInfo in the O3DE Project Manager.
"""

from dataclasses import dataclass, field
from enum import Enum, Flag, auto
from typing import Optional
from pathlib import Path

from ..core import ObjectType


class ObjectOrigin(Enum):
    """Where the object came from."""
    LOCAL = "local"           # Local filesystem
    REMOTE = "remote"         # Remote repository
    CANONICAL = "canonical"   # O3DE canonical repository


class DownloadStatus(Enum):
    """Download status for remote objects."""
    UNKNOWN = "unknown"
    NOT_DOWNLOADED = "not_downloaded"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    DOWNLOAD_FAILED = "download_failed"


class Platform(Flag):
    """Supported platforms."""
    NONE = 0
    WINDOWS = auto()
    LINUX = auto()
    MACOS = auto()
    ANDROID = auto()
    IOS = auto()
    
    @classmethod
    def from_string(cls, platform: str) -> "Platform":
        """Convert platform string to flag."""
        mapping = {
            "windows": cls.WINDOWS,
            "linux": cls.LINUX,
            "macos": cls.MACOS,
            "darwin": cls.MACOS,
            "android": cls.ANDROID,
            "ios": cls.IOS,
        }
        return mapping.get(platform.lower(), cls.NONE)
    
    @classmethod
    def from_strings(cls, platforms: list[str]) -> "Platform":
        """Convert list of platform strings to combined flag."""
        result = cls.NONE
        for p in platforms:
            result |= cls.from_string(p)
        return result


@dataclass
class ObjectInfo:
    """
    Information about an O3DE object for display in the catalog.
    
    This is a display-focused data class that contains everything
    needed to render an object in the GUI.
    """
    # Core identity
    name: str
    display_name: str
    object_type: ObjectType
    version: str = "0.0.0"
    
    # Path and origin
    path: Optional[Path] = None
    origin: ObjectOrigin = ObjectOrigin.LOCAL
    origin_url: str = ""
    
    # Display info
    summary: str = "No summary provided."
    description: str = ""
    creator: str = "Unknown"
    license_text: str = ""
    license_url: str = ""
    
    # Icon - multiple options for loading
    icon_path: Optional[Path] = None  # Absolute path to local icon
    icon_relative_path: str = ""      # Relative path from object root
    icon_url: str = ""                # Remote URL for icon
    
    # Status
    is_added: bool = False
    is_enabled: bool = True
    download_status: DownloadStatus = DownloadStatus.UNKNOWN
    
    # Metadata
    platforms: Platform = Platform.NONE
    last_updated: str = ""
    documentation_url: str = ""
    repository_url: str = ""
    
    # Dependencies and features
    dependencies: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    
    # Engine compatibility
    compatible_engines: list[str] = field(default_factory=list)
    
    # Multiple versions available
    available_versions: list[str] = field(default_factory=list)
    
    # Full release data (version -> release dict)
    # Each release dict has: downloads (dict), source_control (dict)
    releases: dict = field(default_factory=dict)
    
    @property
    def type_display_name(self) -> str:
        """Get display name for the object type."""
        return self.object_type.value.capitalize()
    
    @property
    def name_with_version(self) -> str:
        """Get name with version specifier."""
        return f"{self.name}=={self.version}"
    
    @property
    def is_remote(self) -> bool:
        """Check if object is from a remote source."""
        return self.origin == ObjectOrigin.REMOTE
    
    @property
    def is_local(self) -> bool:
        """Check if object is local."""
        return self.origin == ObjectOrigin.LOCAL
    
    @property
    def is_downloaded(self) -> bool:
        """Check if remote object is downloaded."""
        return self.download_status == DownloadStatus.DOWNLOADED
    
    def supports_platform(self, platform: Platform) -> bool:
        """Check if object supports a specific platform."""
        if self.platforms == Platform.NONE:
            return True  # No platform restrictions
        return bool(self.platforms & platform)
    
    @classmethod
    def from_o3de_object(cls, obj: "O3DEObject", path: Optional[Path] = None) -> "ObjectInfo":
        """
        Create ObjectInfo from an O3DE core object.
        
        Args:
            obj: An O3DE object (Engine, Project, Gem, Template, Repo, Overlay)
            path: Optional path to the object
        """
        from ..core import (
            Engine, Project, Gem, Template, Repo, Overlay,
            get_object_type, get_object_name, get_object_version
        )
        
        object_type = get_object_type(obj)
        name = get_object_name(obj)
        version = get_object_version(obj) or "0.0.0"
        
        # Get display name
        display_name = getattr(obj, 'display_name', None) or name
        
        # Get summary/description
        summary = getattr(obj, 'summary', "No summary provided.")
        
        # Get origin info
        origin_data = getattr(obj, 'origin', None)
        if origin_data:
            origin_url = getattr(origin_data, 'url', "")
        else:
            origin_url = ""
        
        # Determine origin type
        if path and path.exists():
            origin = ObjectOrigin.LOCAL
        elif origin_url:
            origin = ObjectOrigin.REMOTE
        else:
            origin = ObjectOrigin.LOCAL
        
        # Extract other metadata based on object type
        license_text = getattr(obj, 'license', "")
        license_url = getattr(obj, 'license_link', "")
        documentation_url = getattr(obj, 'documentation_url', "")
        repository_url = getattr(obj, 'repo_uri', "")
        
        # Extract dependencies
        deps = getattr(obj, 'dependencies', None)
        if deps:
            dependencies = []
            for dep_type in ['engines', 'projects', 'gems', 'templates']:
                dep_list = getattr(deps, dep_type, [])
                if dep_list:
                    dependencies.extend(dep_list)
        else:
            dependencies = []
        
        # Extract compatible engines
        compatible_engines = getattr(obj, 'compatible_engines', []) or []
        
        # Extract tags
        tags = getattr(obj, 'user_tags', []) or []
        
        # Extract icon - could be nested object or direct attributes
        icon_data = getattr(obj, 'icon', None)
        icon_path = None
        icon_relative_path = ""
        icon_url = ""
        
        if icon_data and hasattr(icon_data, 'relative_path'):
            icon_relative_path = icon_data.relative_path or ""
            icon_url = getattr(icon_data, 'uri', '') or getattr(icon_data, 'url', '') or ""
        elif isinstance(icon_data, dict):
            icon_relative_path = icon_data.get('relative_path', '')
            icon_url = icon_data.get('uri') or icon_data.get('url') or ""
        
        # Compute absolute icon path if we have relative path and object path
        if icon_relative_path and path:
            computed_path = path / icon_relative_path
            if computed_path.exists():
                icon_path = computed_path
        
        return cls(
            name=name,
            display_name=display_name,
            object_type=object_type,
            version=version,
            path=path,
            origin=origin,
            origin_url=origin_url,
            summary=summary,
            license_text=license_text,
            license_url=license_url,
            documentation_url=documentation_url,
            repository_url=repository_url,
            dependencies=dependencies,
            compatible_engines=compatible_engines,
            tags=tags,
            icon_path=icon_path,
            icon_relative_path=icon_relative_path,
            icon_url=icon_url,
        )

    @classmethod
    def from_remote_object(cls, remote: "RemoteObject") -> "ObjectInfo":
        """
        Create ObjectInfo from a RemoteObject from the Store.
        
        Args:
            remote: A RemoteObject from store.py
        """
        # Synthesize releases from source_control_url and download_url
        releases = {}
        available_versions = []
        
        if remote.version:
            available_versions = [remote.version]
            release_data = {}
            
            # Add source_controls if we have a source control URL
            if remote.source_control_url:
                release_data['source_controls'] = [{
                    'git': remote.source_control_url,
                    'tag': '',
                    'branch': '',
                }]
            
            # Add downloads if we have a download URL
            if remote.download_url:
                release_data['downloads'] = [{
                    'source': remote.download_url,
                    'lfs': '',
                }]
            
            if release_data:
                releases[remote.version] = release_data
        
        return cls(
            name=remote.name,
            display_name=remote.display_name or remote.name,
            object_type=remote.object_type,
            version=remote.version,
            path=None,
            origin=ObjectOrigin.REMOTE,
            origin_url=remote.url,
            summary=remote.summary or remote.description or "No summary provided.",
            description=remote.description or remote.summary or "",
            creator=remote.origin or "Unknown",
            license_text=remote.license or "",
            license_url=remote.license_url or "",
            icon_url=remote.icon_url or "",
            icon_relative_path=remote.icon_relative_path or "",
            documentation_url=remote.documentation_url or "",
            repository_url=remote.source_control_url or "",
            tags=remote.tags or [],
            download_status=(
                DownloadStatus.NOT_DOWNLOADED
                if remote.download_url or remote.source_control_url
                else DownloadStatus.UNKNOWN
            ),
            releases=releases,
            available_versions=available_versions,
        )

    @classmethod
    def from_resolved_object(cls, resolved: "ResolvedObject") -> "ObjectInfo":
        """
        Create ObjectInfo from a ResolvedObject.
        
        Args:
            resolved: A ResolvedObject from the resolver
        """
        data = resolved.data
        
        # Schema 2.0.0 nests data under 'engine', 'gem', 'project', etc.
        type_key = resolved.object_type.value  # 'engine', 'gem', 'project', etc.
        nested_data = data.get(type_key, {})
        
        # Get display name (check nested first, then top-level)
        display_name = (
            nested_data.get('display_name') or 
            data.get('display_name') or 
            resolved.name
        )
        
        # Get summary/description (Schema 2.0.0 uses 'description')
        summary = (
            nested_data.get('summary') or
            nested_data.get('description') or
            data.get('summary') or
            data.get('description') or
            "No summary provided."
        )
        
        # Get creator from origin
        origin_data = data.get('origin', {})
        creator = origin_data.get('name', 'Unknown') if isinstance(origin_data, dict) else 'Unknown'
        origin_url = origin_data.get('url', '') if isinstance(origin_data, dict) else ''
        
        # Determine origin type based on path existence
        origin = ObjectOrigin.LOCAL if resolved.path and resolved.path.exists() else ObjectOrigin.REMOTE
        
        # Extract metadata
        license_text = data.get('license', '')
        license_url = data.get('license_link', '')
        documentation_url = data.get('documentation_url', '')
        repository_url = data.get('repo_uri', '')
        
        # Extract dependencies from data
        deps_data = data.get('dependencies', {})
        dependencies = []
        if isinstance(deps_data, dict):
            for dep_type in ['engines', 'projects', 'gems', 'templates']:
                dep_list = deps_data.get(dep_type, [])
                if dep_list:
                    dependencies.extend(dep_list)
        
        # Extract compatible engines
        compatible_engines = data.get('compatible_engines', []) or []
        
        # Extract tags
        tags = data.get('user_tags', []) or []
        
        # Extract icon - Schema 2.0.0 uses nested 'icon' object
        icon_data = data.get('icon', {})
        if isinstance(icon_data, dict):
            icon_relative_path = icon_data.get('relative_path') or ''
            icon_url = icon_data.get('uri') or icon_data.get('url') or ''
        else:
            icon_relative_path = ''
            icon_url = str(icon_data) if icon_data else ''
        
        # Compute absolute icon_path if we have a relative path and object path
        icon_path = None
        if icon_relative_path and resolved.path:
            computed_path = resolved.path / icon_relative_path
            if computed_path.exists():
                icon_path = computed_path
        
        # Extract releases for available versions and release data
        releases_list = data.get('releases', [])
        available_versions = []
        releases_dict = {}
        if releases_list and isinstance(releases_list, list):
            for release in releases_list:
                # Support both 'name' (2.0.0 schema) and 'version' (legacy) fields
                if isinstance(release, dict) and (release.get('name') or release.get('version')):
                    version = release.get('name') or release['version']
                    available_versions.append(version)
                    releases_dict[version] = {
                        'downloads': release.get('downloads', []),
                        'binaries': release.get('binaries', []),
                        'source_control': release.get('source_control', {}),
                        'source_controls': release.get('source_controls', []),
                    }
        
        return cls(
            name=resolved.name,
            display_name=display_name,
            object_type=resolved.object_type,
            version=resolved.version,
            path=resolved.path,
            origin=origin,
            origin_url=origin_url,
            summary=summary,
            creator=creator,
            license_text=license_text,
            license_url=license_url,
            documentation_url=documentation_url,
            repository_url=repository_url,
            dependencies=dependencies,
            compatible_engines=compatible_engines,
            tags=tags,
            icon_path=icon_path,
            available_versions=available_versions,
            releases=releases_dict,
        )
