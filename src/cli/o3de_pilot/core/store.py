# O3DE Pilot - Store / Remote Object Fetcher
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
O3DE Store Interface.

The Store is a tree of repo.json files describing available O3DE objects.
Starting from the manifest's remote repos, we descend all remote links,
caching JSON files locally for offline use.

Store operations:
1. Refresh - Download/update all remote object metadata
2. Search - Find objects by name, tags, type
3. Download - Clone git repo or download release archive
4. Cache - Maintain local cache of remote metadata

Cache structure (~/.o3de/Cache/):
  <sha256_of_url>/
    object.json     - Cached JSON
    metadata.json   - Cache metadata (timestamp, etag, etc)
"""

from pathlib import Path
from typing import Optional, Callable, Any
from urllib.parse import urlparse
import hashlib
import json
import logging
import time
from datetime import datetime, timezone

import httpx

from .paths import get_cache_path, get_download_path
from .models import (
    O3DEObject, ObjectType, Repo, Engine, Project, Gem, Template, Overlay,
    get_object_type, get_object_name, get_object_version, Remote
)

logger = logging.getLogger("o3de_pilot.store")


class StoreError(Exception):
    """Error during store operations."""
    pass


class FetchError(StoreError):
    """Error fetching remote resource."""
    pass


class RemoteObject:
    """Metadata about a remote object."""
    
    def __init__(
        self,
        url: str,
        object_type: ObjectType,
        name: str = "",
        version: str = "",
        display_name: str = "",
        summary: str = "",
        description: str = "",
        origin: str = "",
        origin_url: str = "",
        license: str = "",
        license_url: str = "",
        icon_url: str = "",
        icon_relative_path: str = "",
        documentation_url: str = "",
        source_control_url: Optional[str] = None,
        download_url: Optional[str] = None,
        gem_type: str = "",
        tags: Optional[list[str]] = None,
        cached_at: Optional[datetime] = None,
    ):
        self.url = url
        self.object_type = object_type
        self.name = name
        self.version = version
        self.display_name = display_name
        self.summary = summary
        self.description = description
        self.origin = origin
        self.origin_url = origin_url
        self.license = license
        self.license_url = license_url
        self.icon_url = icon_url
        self.icon_relative_path = icon_relative_path
        self.documentation_url = documentation_url
        self.source_control_url = source_control_url
        self.download_url = download_url
        self.gem_type = gem_type
        self.tags = tags or []
        self.cached_at = cached_at
    
    def __repr__(self) -> str:
        return f"RemoteObject({self.object_type.value}:{self.name}@{self.version})"


class Cache:
    """Local cache for remote JSON files."""
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or get_cache_path()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _url_to_cache_path(self, url: str) -> Path:
        """Convert URL to cache directory path."""
        url_hash = hashlib.sha256(url.encode()).hexdigest()
        return self.cache_dir / url_hash
    
    def get(self, url: str) -> Optional[dict]:
        """Get cached JSON for URL, or None if not cached."""
        cache_path = self._url_to_cache_path(url)
        json_path = cache_path / "object.json"
        
        if json_path.exists():
            try:
                with open(json_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"Failed to read cache for {url}: {e}")
        
        return None
    
    def get_metadata(self, url: str) -> Optional[dict]:
        """Get cache metadata for URL."""
        cache_path = self._url_to_cache_path(url)
        meta_path = cache_path / "metadata.json"
        
        if meta_path.exists():
            try:
                with open(meta_path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        
        return None
    
    def put(self, url: str, data: dict, etag: Optional[str] = None) -> None:
        """Store JSON in cache."""
        cache_path = self._url_to_cache_path(url)
        cache_path.mkdir(parents=True, exist_ok=True)
        
        # Write object JSON
        json_path = cache_path / "object.json"
        with open(json_path, "w") as f:
            json.dump(data, f, indent=2)
        
        # Write metadata
        meta_path = cache_path / "metadata.json"
        metadata = {
            "url": url,
            "cached_at": datetime.now(timezone.utc).isoformat(),
            "etag": etag,
        }
        with open(meta_path, "w") as f:
            json.dump(metadata, f, indent=2)
    
    def is_stale(self, url: str, max_age_hours: int = 24) -> bool:
        """Check if cache entry is stale."""
        meta = self.get_metadata(url)
        if not meta:
            return True
        
        cached_at = datetime.fromisoformat(meta.get("cached_at", "1970-01-01T00:00:00+00:00"))
        age = datetime.now(timezone.utc) - cached_at
        return age.total_seconds() > (max_age_hours * 3600)
    
    def clear(self, url: Optional[str] = None) -> int:
        """Clear cache. If url provided, clear only that entry. Returns count cleared."""
        import shutil
        
        if url:
            cache_path = self._url_to_cache_path(url)
            if cache_path.exists():
                shutil.rmtree(cache_path)
                return 1
            return 0
        else:
            count = 0
            for entry in self.cache_dir.iterdir():
                if entry.is_dir():
                    shutil.rmtree(entry)
                    count += 1
            return count


class Store:
    """
    O3DE Store interface for browsing and downloading remote objects.
    
    Usage:
        store = Store()
        await store.refresh()  # Download all remote metadata
        
        gems = store.search("physics", object_type=ObjectType.GEM)
        await store.download(gems[0], target_path)
    """
    
    def __init__(
        self,
        cache: Optional[Cache] = None,
        timeout: float = 30.0,
    ):
        self.cache = cache or Cache()
        self.timeout = timeout
        
        # All discovered remote objects (keyed by type:name, latest version only)
        self.objects: dict[str, RemoteObject] = {}
        
        # All versions of each object: {"type:name": {"version": RemoteObject}}
        self.versions: dict[str, dict[str, RemoteObject]] = {}
        
        # URLs we've already visited (to avoid cycles)
        self._visited_urls: set[str] = set()
    
    async def fetch_json(
        self,
        url: str,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> dict:
        """
        Fetch JSON from URL, using cache if available.
        
        Args:
            url: URL to fetch
            use_cache: Whether to use cached version
            force_refresh: Force download even if cached
        
        Returns:
            Parsed JSON dict
        """
        # Check cache first
        if use_cache and not force_refresh:
            cached = self.cache.get(url)
            if cached and not self.cache.is_stale(url):
                logger.debug(f"Using cached: {url}")
                return cached
        
        # Fetch from remote
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                
                data = response.json()
                etag = response.headers.get("etag")
                
                # Cache the result
                self.cache.put(url, data, etag)
                
                return data
                
        except httpx.HTTPError as e:
            # Try to use stale cache
            if use_cache:
                cached = self.cache.get(url)
                if cached:
                    logger.warning(f"Fetch failed, using stale cache: {url}")
                    return cached
            
            raise FetchError(f"Failed to fetch {url}: {e}")
        except json.JSONDecodeError as e:
            raise FetchError(f"Invalid JSON at {url}: {e}")
    
    def fetch_json_sync(
        self,
        url: str,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> dict:
        """Synchronous version of fetch_json."""
        # Check cache first
        if use_cache and not force_refresh:
            cached = self.cache.get(url)
            if cached and not self.cache.is_stale(url):
                logger.debug(f"Using cached: {url}")
                return cached
        
        # Fetch from remote
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
                response.raise_for_status()
                
                data = response.json()
                etag = response.headers.get("etag")
                
                # Cache the result
                self.cache.put(url, data, etag)
                
                return data
                
        except httpx.HTTPError as e:
            # Try to use stale cache
            if use_cache:
                cached = self.cache.get(url)
                if cached:
                    logger.warning(f"Fetch failed, using stale cache: {url}")
                    return cached
            
            raise FetchError(f"Failed to fetch {url}: {e}")
    
    async def refresh(
        self,
        repo_urls: list[str],
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> int:
        """
        Refresh store by descending all repo trees.
        
        Args:
            repo_urls: Starting repo.json URLs
            progress_callback: Optional callback(message, current, total)
        
        Returns:
            Number of objects discovered
        """
        self._visited_urls.clear()
        self.objects.clear()
        
        # Queue of URLs to process
        queue = list(repo_urls)
        total = len(queue)
        processed = 0
        
        while queue:
            url = queue.pop(0)
            
            if url in self._visited_urls:
                continue
            
            self._visited_urls.add(url)
            processed += 1
            
            if progress_callback:
                progress_callback(f"Fetching {urlparse(url).path}", processed, total)
            
            try:
                data = await self.fetch_json(url)
            except FetchError as e:
                logger.warning(f"Skipping {url}: {e}")
                continue
            
            # Parse object and extract remote links
            obj_type = get_object_type(data)
            remote_obj = self._parse_remote_object(url, data, obj_type)
            
            if remote_obj:
                key = f"{remote_obj.object_type.value}:{remote_obj.name}"
                version = remote_obj.version or "0.0.0"
                
                # Track all versions
                if key not in self.versions:
                    self.versions[key] = {}
                self.versions[key][version] = remote_obj
                
                # Keep latest version in objects dict for backwards compatibility
                if key not in self.objects or self._is_newer_version(version, self.objects[key].version):
                    self.objects[key] = remote_obj
            
            # Queue any remote links
            new_urls = self._extract_remote_urls(data)
            for new_url in new_urls:
                if new_url not in self._visited_urls:
                    queue.append(new_url)
                    total += 1
        
        if progress_callback:
            progress_callback("Complete", total, total)
        
        logger.info(f"Store refresh complete: {len(self.objects)} objects")
        return len(self.objects)
    
    def refresh_sync(
        self,
        repo_urls: list[str],
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> int:
        """Synchronous version of refresh."""
        self._visited_urls.clear()
        self.objects.clear()
        
        queue = list(repo_urls)
        total = len(queue)
        processed = 0
        
        while queue:
            url = queue.pop(0)
            
            if url in self._visited_urls:
                continue
            
            self._visited_urls.add(url)
            processed += 1
            
            if progress_callback:
                progress_callback(f"Fetching {urlparse(url).path}", processed, total)
            
            try:
                data = self.fetch_json_sync(url)
            except FetchError as e:
                logger.warning(f"Skipping {url}: {e}")
                continue
            
            obj_type = get_object_type(data)
            remote_obj = self._parse_remote_object(url, data, obj_type)
            
            if remote_obj:
                key = f"{remote_obj.object_type.value}:{remote_obj.name}"
                version = remote_obj.version or "0.0.0"
                
                # Track all versions
                if key not in self.versions:
                    self.versions[key] = {}
                self.versions[key][version] = remote_obj
                
                # Keep latest version in objects dict for backwards compatibility
                if key not in self.objects or self._is_newer_version(version, self.objects[key].version):
                    self.objects[key] = remote_obj
            
            new_urls = self._extract_remote_urls(data)
            for new_url in new_urls:
                if new_url not in self._visited_urls:
                    queue.append(new_url)
                    total += 1
        
        return len(self.objects)
    
    def _parse_remote_object(
        self,
        url: str,
        data: dict,
        obj_type: ObjectType
    ) -> Optional[RemoteObject]:
        """Parse JSON into RemoteObject."""
        try:
            name = get_object_name(data)
            version = get_object_version(data)
            
            # Try nested structure first (Schema 2.0.0), then flat structure (legacy)
            header_key = obj_type.value if obj_type != ObjectType.MANIFEST else "o3de_manifest"
            nested = data.get(header_key, {})
            
            # Helper to get value from nested or top-level
            def get_val(key: str, default: str = "") -> str:
                return nested.get(key) or data.get(key) or default
            
            display_name = get_val("display_name", name)
            summary = get_val("summary")
            description = get_val("description", summary)
            origin = get_val("origin")
            origin_url = get_val("origin_url")
            license_text = get_val("license")
            license_url = get_val("license_url", get_val("license_link"))
            
            # Extract icon - can be nested object or flat string
            icon_data = nested.get("icon") or data.get("icon") or {}
            if isinstance(icon_data, dict):
                icon_url = icon_data.get("uri") or icon_data.get("url") or ""
                icon_relative_path = icon_data.get("relative_path") or ""
            else:
                # Legacy: might be a direct URL string
                icon_url = str(icon_data) if icon_data else ""
                icon_relative_path = ""
            
            # Fallback to flat fields if icon was not found
            if not icon_url:
                icon_url = get_val("icon_uri", get_val("icon_url"))
            
            documentation_url = get_val("documentation_url")
            gem_type = get_val("type")
            
            # Extract tags
            tags = data.get("user_tags") or data.get("canonical_tags") or []
            if isinstance(tags, str):
                tags = [tags]
            
            # Extract download URLs - try multiple field names
            source_control_url = (
                get_val("download_source_uri") or
                get_val("repo_uri") or
                (data.get("source_control", {}) or {}).get("uri")
            )
            
            download_url = (
                get_val("download_uri") or
                (data.get("download", {}) or {}).get("source")
            )
            
            return RemoteObject(
                url=url,
                object_type=obj_type,
                name=name,
                version=version,
                display_name=display_name,
                summary=summary,
                description=description,
                origin=origin,
                origin_url=origin_url,
                license=license_text,
                license_url=license_url,
                icon_url=icon_url,
                icon_relative_path=icon_relative_path,
                documentation_url=documentation_url,
                source_control_url=source_control_url,
                download_url=download_url,
                gem_type=gem_type,
                tags=tags,
                cached_at=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.warning(f"Failed to parse object at {url}: {e}")
            return None
    
    def _extract_remote_urls(self, data: dict) -> list[str]:
        """Extract all remote object URLs from JSON."""
        urls = []
        
        # Check for nested remote structure (manifest style)
        remote = data.get("remote", {})
        if isinstance(remote, dict):
            for key in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
                urls.extend(remote.get(key, []))
        
        # Also check top-level arrays (repo.json style)
        for key in ["engines", "projects", "gems", "templates", "repos", "overlays"]:
            top_level = data.get(key, [])
            if isinstance(top_level, list):
                urls.extend(top_level)
        
        return urls
    
    def search(
        self,
        query: str = "",
        object_type: Optional[ObjectType] = None,
        tags: Optional[list[str]] = None,
    ) -> list[RemoteObject]:
        """
        Search for objects in the store.
        
        Args:
            query: Text to search in name, display_name, description
            object_type: Filter by object type
            tags: Filter by tags (any match)
        
        Returns:
            List of matching RemoteObjects
        """
        results = []
        query_lower = query.lower()
        
        for obj in self.objects.values():
            # Filter by type
            if object_type and obj.object_type != object_type:
                continue
            
            # Filter by query
            if query:
                searchable = f"{obj.name} {obj.display_name} {obj.description}".lower()
                if query_lower not in searchable:
                    continue
            
            results.append(obj)
        
        # Sort by relevance (name match first, then alphabetically)
        results.sort(key=lambda o: (
            0 if query_lower in o.name.lower() else 1,
            o.name
        ))
        
        return results
    
    def get_by_name(self, object_type: ObjectType, name: str) -> Optional[RemoteObject]:
        """Get a specific object by type and name."""
        key = f"{object_type.value}:{name}"
        return self.objects.get(key)
    
    def get_versions(self, object_type: ObjectType, name: str) -> list[str]:
        """Get all available versions for an object, sorted newest first."""
        key = f"{object_type.value}:{name}"
        versions_dict = self.versions.get(key, {})
        versions = list(versions_dict.keys())
        # Sort by version (try semver-style, fallback to string)
        versions.sort(key=self._version_sort_key, reverse=True)
        return versions
    
    def get_version(self, object_type: ObjectType, name: str, version: str) -> Optional[RemoteObject]:
        """Get a specific version of an object."""
        key = f"{object_type.value}:{name}"
        versions_dict = self.versions.get(key, {})
        return versions_dict.get(version)
    
    def _is_newer_version(self, v1: str, v2: str) -> bool:
        """Check if v1 is newer than v2."""
        return self._version_sort_key(v1) > self._version_sort_key(v2)
    
    def _version_sort_key(self, version: str) -> tuple:
        """Generate a sort key for version strings."""
        # Try to parse as semver-like version
        parts = version.split(".")
        result = []
        for part in parts:
            # Extract leading number
            num = ""
            suffix = ""
            for i, c in enumerate(part):
                if c.isdigit():
                    num += c
                else:
                    suffix = part[i:]
                    break
            result.append((int(num) if num else 0, suffix))
        # Pad to ensure consistent comparison
        while len(result) < 4:
            result.append((0, ""))
        return tuple(result)
    
    async def download(
        self,
        remote_obj: RemoteObject,
        target_path: Path,
        prefer_source_control: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> Path:
        """
        Download a remote object to local disk.
        
        Args:
            remote_obj: Object to download
            target_path: Where to download (parent directory)
            prefer_source_control: Prefer git clone over archive download
            progress_callback: Progress callback
        
        Returns:
            Path to downloaded object
        """
        import subprocess
        import zipfile
        
        # Determine download method
        if prefer_source_control and remote_obj.source_control_url:
            # Git clone
            clone_url = remote_obj.source_control_url
            obj_name = remote_obj.name.split(".")[-1]  # Last segment of reverse domain
            clone_path = target_path / obj_name
            
            if progress_callback:
                progress_callback(f"Cloning {clone_url}", 0, 1)
            
            result = subprocess.run(
                ["git", "clone", clone_url, str(clone_path)],
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                raise StoreError(f"Git clone failed: {result.stderr}")
            
            if progress_callback:
                progress_callback("Clone complete", 1, 1)
            
            return clone_path
            
        elif remote_obj.download_url:
            # Download archive
            download_url = remote_obj.download_url
            
            if progress_callback:
                progress_callback(f"Downloading {download_url}", 0, 1)
            
            # Download to temp location
            download_dir = get_download_path()
            archive_path = download_dir / f"{remote_obj.name}.zip"
            
            async with httpx.AsyncClient(timeout=300) as client:
                async with client.stream("GET", download_url) as response:
                    response.raise_for_status()
                    with open(archive_path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)
            
            # Extract
            obj_name = remote_obj.name.split(".")[-1]
            extract_path = target_path / obj_name
            
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_path)
            
            # Cleanup
            archive_path.unlink()
            
            if progress_callback:
                progress_callback("Download complete", 1, 1)
            
            return extract_path
        else:
            raise StoreError(f"No download method available for {remote_obj.name}")

    def download_sync(
        self,
        remote_obj: RemoteObject,
        target_path: Path,
        prefer_source_control: bool = True,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
        use_version_folders: bool = True,
    ) -> Path:
        """
        Synchronous version of download.
        
        Args:
            remote_obj: Object to download
            target_path: Where to download (parent directory)
            prefer_source_control: Prefer git clone over archive download
            progress_callback: Progress callback
            use_version_folders: If True, creates <name>/<version>/ structure
        
        Returns:
            Path to downloaded object
        """
        import subprocess
        import zipfile
        
        target_path = Path(target_path)
        target_path.mkdir(parents=True, exist_ok=True)
        
        # Compute folder structure
        obj_name = remote_obj.name.replace(".", "_")
        version = remote_obj.version or "0.0.0"
        
        if use_version_folders:
            # Structure: <target>/<name>/<version>/
            obj_folder = target_path / obj_name / version
        else:
            # Structure: <target>/<name>/
            obj_folder = target_path / obj_name
        
        # Determine download method
        if prefer_source_control and remote_obj.source_control_url:
            # Git clone
            clone_url = remote_obj.source_control_url
            clone_path = obj_folder
            
            if progress_callback:
                progress_callback(f"Cloning {clone_url}", 0, 1)
            
            # Ensure parent directory exists
            clone_path.parent.mkdir(parents=True, exist_ok=True)
            
            result = subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, str(clone_path)],
                capture_output=True,
                text=True,
            )
            
            if result.returncode != 0:
                raise StoreError(f"Git clone failed: {result.stderr}")
            
            if progress_callback:
                progress_callback("Clone complete", 1, 1)
            
            return clone_path
            
        elif remote_obj.download_url:
            # Download archive
            download_url = remote_obj.download_url
            
            if progress_callback:
                progress_callback(f"Downloading {download_url}", 0, 1)
            
            # Download to temp location
            download_dir = get_download_path()
            download_dir.mkdir(parents=True, exist_ok=True)
            archive_path = download_dir / f"{remote_obj.name}.zip"
            
            with httpx.Client(timeout=300) as client:
                with client.stream("GET", download_url) as response:
                    response.raise_for_status()
                    with open(archive_path, "wb") as f:
                        for chunk in response.iter_bytes():
                            f.write(chunk)
            
            # Extract to versioned folder
            extract_path = obj_folder
            extract_path.parent.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(archive_path, "r") as zf:
                zf.extractall(extract_path)
            
            # Cleanup
            archive_path.unlink()
            
            if progress_callback:
                progress_callback("Download complete", 1, 1)
            
            return extract_path
        else:
            raise StoreError(f"No download method available for {remote_obj.name}")

