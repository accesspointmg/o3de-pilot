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

from o3de_cli.core import ObjectType


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
    licenses: list[dict] = field(default_factory=list)  # [{"text": ..., "url": ...}, ...]
    
    # Icon - multiple options for loading
    icon_path: Optional[Path] = None  # Absolute path to local icon
    icon_relative_path: str = ""      # Relative path from object root
    icon_url: str = ""                # Remote URL for icon
    
    # Status
    is_enabled: bool = True
    download_status: DownloadStatus = DownloadStatus.UNKNOWN
    download_progress: int = 0  # 0-100 progress value
    
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
    local_versions: list[str] = field(default_factory=list)  # Versions available locally
    github_only_versions: list[str] = field(default_factory=list)  # Versions from GitHub not in JSON
    json_releases: list[str] = field(default_factory=list)  # Releases from object's JSON file (preserved)
    
    # Download/source info (from downloads and source_control sections)
    source_zip_url: str = ""  # downloads.source_zip_uri
    git_branch: str = ""      # source_control.branch
    is_repo_cloned: Optional[bool] = None  # True if repo+branch cloned locally, False if not, None if unknown
    
    # Full release data (version -> release dict)
    # Each release dict has: downloads (dict), source_control (dict)
    releases: dict = field(default_factory=dict)
    
    # Deprecation status
    is_deprecated: bool = False
    deprecation_message: str = ""
    replacement_name: str = ""  # Suggested replacement object
    
    # Integrity status
    has_integrity: bool = False  # Whether integrity checksums are present
    integrity_algorithm: str = ""  # e.g., "sha256"
    
    # Optional and peer dependencies
    optional_dependencies: list[str] = field(default_factory=list)
    peer_dependencies: list[str] = field(default_factory=list)
    
    # Registration status
    is_manifest_registered: bool = False  # True if directly listed in manifest (parent is None)
    
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
    
    def resolve_git_branch(self) -> str:
        """
        Resolve and set the git branch for this object.
        
        If git_branch is already set, returns it.
        If repository_url is a git URL and branch is not set, fetches the default branch.
        
        Returns:
            The resolved git branch, or empty string if none.
        """
        # Already have a branch
        if self.git_branch:
            return self.git_branch
        
        # No repository URL, can't determine branch
        if not self.repository_url:
            return ""
        
        # Try to fetch default branch from git
        from o3de_cli.core.git_utils import get_default_branch, is_git_url
        
        if is_git_url(self.repository_url):
            branch = get_default_branch(self.repository_url)
            if branch:
                self.git_branch = branch
                return branch
        
        return ""

    @classmethod
    def from_o3de_object(cls, obj: "O3DEObject", path: Optional[Path] = None) -> "ObjectInfo":
        """
        Create ObjectInfo from an O3DE core object.
        
        Args:
            obj: An O3DE object (Engine, Project, Gem, Template, Repo, Overlay)
            path: Optional path to the object
        """
        from o3de_cli.core import (
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
        
        # Use effective source control (own or inherited from parent)
        effective_sc_url = remote.effective_source_control_url or ''
        effective_sc_branch = remote.effective_source_control_branch or ''
        
        if remote.version:
            available_versions = [remote.version]
            release_data = {}
            
            # Add source_controls if we have a source control URL
            if effective_sc_url:
                release_data['source_controls'] = [{
                    'git': effective_sc_url,
                    'tag': '',
                    'branch': effective_sc_branch,
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
            repository_url=effective_sc_url,
            tags=remote.tags or [],
            git_branch=effective_sc_branch,
            download_status=(
                DownloadStatus.NOT_DOWNLOADED
                if remote.download_url or effective_sc_url
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
        
        # For local objects, the current version is local
        local_versions = [resolved.version] if resolved.version else []
        
        # Extract downloads info (source_zip_uri)
        downloads_data = data.get('downloads', {})
        source_zip_url = ""
        if isinstance(downloads_data, dict):
            source_zip_url = downloads_data.get('source_zip_uri', '') or ''
        
        # Extract source control info (git_uri, branch)
        source_control_data = data.get('source_control', {})
        git_branch = ""
        if isinstance(source_control_data, dict):
            git_branch = source_control_data.get('branch', '') or ''
        
        # For local objects, get git info from the local repository
        if origin == ObjectOrigin.LOCAL and resolved.path:
            from o3de_cli.core.git_utils import get_local_git_remote, get_local_git_branch
            
            # Get repository URL from local git if not set
            if not repository_url:
                local_remote = get_local_git_remote(str(resolved.path))
                if local_remote:
                    repository_url = local_remote
            
            # Get current branch from local git if not set
            if not git_branch:
                local_branch = get_local_git_branch(str(resolved.path))
                if local_branch:
                    git_branch = local_branch
        
        # Local objects with git info are by definition cloned locally
        is_cloned = True if (origin == ObjectOrigin.LOCAL and repository_url) else None
        
        # Deprecation status
        deprecated_data = data.get('deprecated', nested_data.get('deprecated', {}))
        is_deprecated = False
        deprecation_message = ""
        replacement_name = ""
        if deprecated_data:
            if isinstance(deprecated_data, dict):
                is_deprecated = True
                deprecation_message = deprecated_data.get('message', deprecated_data.get('description', ''))
                replacement_name = deprecated_data.get('replacement', '')
            elif isinstance(deprecated_data, bool):
                is_deprecated = deprecated_data
        
        # Integrity status from releases
        has_integrity = False
        integrity_algorithm = ""
        if releases_list and isinstance(releases_list, list):
            for release in releases_list:
                if isinstance(release, dict):
                    integrity = release.get('integrity', {})
                    if isinstance(integrity, dict) and integrity.get('hash'):
                        has_integrity = True
                        integrity_algorithm = integrity.get('algorithm', 'sha256')
                        break
                    # Also check downloads for integrity
                    for dl in release.get('downloads', []):
                        if isinstance(dl, dict) and dl.get('integrity'):
                            has_integrity = True
                            integrity_algorithm = dl['integrity'].get('algorithm', 'sha256')
                            break
                    if has_integrity:
                        break
        
        # Optional and peer dependencies from resolved object
        optional_deps = [f"{d.name}=={d.version}" for d in resolved.optional_dependencies] if resolved.optional_dependencies else []
        peer_deps = [f"{d.name}=={d.version}" for d in resolved.peer_dependencies] if resolved.peer_dependencies else []
        
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
            local_versions=local_versions,
            source_zip_url=source_zip_url,
            git_branch=git_branch,
            is_repo_cloned=is_cloned,
            releases=releases_dict,
            is_deprecated=is_deprecated,
            deprecation_message=deprecation_message,
            replacement_name=replacement_name,
            has_integrity=has_integrity,
            integrity_algorithm=integrity_algorithm,
            optional_dependencies=optional_deps,
            peer_dependencies=peer_deps,
        )

    @classmethod
    def from_resolved_dict(cls, name: str, obj_data: dict) -> "ObjectInfo":
        """
        Create ObjectInfo from precomputed resolved manifest dict data.
        
        This is the fast path - uses precomputed display_metadata, git_info,
        parents, etc. from the cached resolved manifest.
        
        Args:
            name: Object name (key in resolved manifest's objects dict)
            obj_data: Precomputed object dict from resolved_o3de_manifest.json
        """
        from pathlib import Path
        from o3de_cli.core.models import ObjectType
        
        # Get basic info
        path_str = obj_data.get("path", "")
        path = Path(path_str) if path_str else None
        object_type = ObjectType(obj_data.get("type", "gem"))
        version = obj_data.get("version", "0.0.0")
        
        # Use precomputed display_metadata
        display_meta = obj_data.get("display_metadata") or {}
        display_name = display_meta.get("display_name", name)
        summary = display_meta.get("summary", "No summary provided.")
        icon_relative = display_meta.get("icon_path", "")
        
        # Compute absolute icon path
        icon_path = None
        if icon_relative and path:
            computed = path / icon_relative
            if computed.exists():
                icon_path = computed
        
        # Use precomputed git_info
        git_info = obj_data.get("git_info") or {}
        repository_url = git_info.get("remote_url", "")
        git_branch = git_info.get("branch", "")
        
        # Use precomputed dependencies/dependents
        dependencies = obj_data.get("dependencies", [])
        
        # Determine origin
        origin = ObjectOrigin.LOCAL if (path and path.exists()) else ObjectOrigin.REMOTE
        is_cloned = True if (origin == ObjectOrigin.LOCAL and repository_url) else None
        
        # Local versions
        local_versions = [version] if version else []
        
        # Releases from cached resolved manifest
        release_versions = obj_data.get("releases") or []
        
        # Deprecation status from cached data
        is_deprecated = obj_data.get("is_deprecated", False)
        deprecation_message = obj_data.get("deprecation_message", "")
        replacement_name = obj_data.get("replacement_name", "")
        
        # Integrity and optional/peer deps from cached data
        has_integrity = obj_data.get("has_integrity", False)
        optional_deps = obj_data.get("optional_dependencies", [])
        peer_deps = obj_data.get("peer_dependencies", [])
        
        # Extract origin info (effective, includes inherited values)
        origin_data = obj_data.get("origin") or {}
        creator = origin_data.get("name", "") if isinstance(origin_data, dict) else ""
        origin_url = origin_data.get("url", "") if isinstance(origin_data, dict) else ""

        # Extract licenses (effective, includes inherited values)
        licenses_list = obj_data.get("licenses") or []
        license_text = ""
        license_url = ""
        all_licenses: list[dict] = []
        if licenses_list and isinstance(licenses_list, list):
            for lic_entry in licenses_list:
                if isinstance(lic_entry, dict):
                    lic_text = (
                        lic_entry.get("license_identifier", "")
                        or lic_entry.get("display_name", "")
                    )
                    lic_url = lic_entry.get("url", "")
                    if lic_text:
                        all_licenses.append({"text": lic_text, "url": lic_url})
            if all_licenses:
                license_text = all_licenses[0]["text"]
                license_url = all_licenses[0]["url"]

        # Extract documentation (effective, includes inherited values)
        doc_data = obj_data.get("documentation") or {}
        documentation_url = (
            doc_data.get("url", "") if isinstance(doc_data, dict) else ""
        )

        # Extract source_control as fallback for repository_url
        if not repository_url:
            sc_data = obj_data.get("source_control") or {}
            if isinstance(sc_data, dict):
                repository_url = sc_data.get("url") or sc_data.get("git") or ""
        
        # Directly registered = parent is None (root object in manifest)
        is_manifest_registered = obj_data.get("parent") is None and origin == ObjectOrigin.LOCAL
        
        return cls(
            name=name,
            display_name=display_name,
            object_type=object_type,
            version=version,
            path=path,
            origin=origin,
            origin_url=origin_url,
            summary=summary,
            creator=creator,
            license_text=license_text,
            license_url=license_url,
            licenses=all_licenses,
            documentation_url=documentation_url,
            repository_url=repository_url,
            dependencies=dependencies,
            compatible_engines=[],
            tags=[],
            icon_path=icon_path,
            available_versions=release_versions,
            local_versions=local_versions,
            json_releases=release_versions.copy(),
            source_zip_url="",
            git_branch=git_branch,
            is_repo_cloned=is_cloned,
            releases={},
            is_deprecated=is_deprecated,
            deprecation_message=deprecation_message,
            replacement_name=replacement_name,
            has_integrity=has_integrity,
            optional_dependencies=optional_deps,
            peer_dependencies=peer_deps,
            is_manifest_registered=is_manifest_registered,
        )
