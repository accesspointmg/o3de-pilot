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


class DependencyConflict:
    """Represents a version conflict between two dependency requirements."""
    
    def __init__(
        self,
        dependency_name: str,
        requirer_a: str,
        constraint_a: str,
        requirer_b: str,
        constraint_b: str,
        resolved_version: str | None = None,
    ):
        self.dependency_name = dependency_name
        self.requirer_a = requirer_a
        self.constraint_a = constraint_a
        self.requirer_b = requirer_b
        self.constraint_b = constraint_b
        self.resolved_version = resolved_version
    
    def __repr__(self) -> str:
        return (
            f"DependencyConflict({self.dependency_name}: "
            f"{self.requirer_a} wants {self.constraint_a}, "
            f"{self.requirer_b} wants {self.constraint_b})"
        )


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
        
        # Optional dependencies (nice-to-have, not required)
        self.optional_dependencies: list[ObjectNameVersion] = []
        
        # Peer dependencies (must be provided by consumer, warning if missing)
        self.peer_dependencies: list[ObjectNameVersion] = []
        
        # Overlays that extend this object
        self.overlays: list["ResolvedObject"] = []
        
        # Parent object that contains this one (set during resolution)
        self.parent: Optional["ResolvedObject"] = None
        
        # Properties inherited from parent (property_name -> parent_name)
        # Only set for properties the child did NOT define and got from a parent.
        self.inherited_from: dict[str, str] = {}
    
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
    
    def __init__(self, manifest_path: Optional[Path] = None, dry_run: bool = False):
        self.manifest_path = manifest_path or get_manifest_path()
        self.resolved_path = get_resolved_manifest_path()
        self.dry_run = dry_run
        
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
        
        # Dependency graph: object_name -> list of (dep_name, dep_version) tuples
        self.dependency_graph: dict[str, list[tuple[str, str]]] = {}
        
        # Detected conflicts
        self.conflicts: list[DependencyConflict] = []
        
        # Locked (pinned) transitive dependencies
        self.locked_dependencies: dict[str, dict] = {}
        
        # Remote repo URLs from the manifest (not local paths)
        self.manifest_remotes: list[str] = []
        
        # Crawled remote repos: url -> {repo_name, summary, repos: [...], gems: [...], ...}
        self._crawled_remotes: dict[str, dict] = {}
    
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

        # Upgrade manifest to sidecar if needed
        if needs_upgrade(self.manifest_data):
            upgraded_manifest = upgrade_to_latest(self.manifest_data, "manifest")
            if upgraded_manifest is not None:
                sidecar_name = "o3de_manifest.2-0-0.json"
                sidecar_path = self.manifest_path.parent / sidecar_name
                try:
                    with open(sidecar_path, "w") as f:
                        json.dump(upgraded_manifest, f, indent=2)
                    logger.info(f"Created manifest sidecar: {sidecar_path}")
                    # Ensure default directories (repos, overlays) exist on disk
                    for key in ("repos_path", "overlays_path"):
                        dir_str = upgraded_manifest.get("default", {}).get(key, "")
                        if dir_str:
                            Path(dir_str).mkdir(parents=True, exist_ok=True)
                except IOError as e:
                    logger.warning(f"Failed to write manifest sidecar: {e}")
        
        # Handle both Schema 2.0.0 (local.engines) and legacy (engines at root) formats
        local = self.manifest_data.get("local", {})
        remote = self.manifest_data.get("remote", {})
        
        # Sanitize manifest: deduplicate and validate type assignments
        dirty = self._sanitize_manifest(local)
        if dirty:
            try:
                with open(self.manifest_path, "w") as f:
                    json.dump(self.manifest_data, f, indent=2)
                logger.info("Sanitized manifest (dedup / type fix)")
            except IOError as e:
                logger.warning(f"Failed to save sanitized manifest: {e}")
        
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
                # URLs (http/https) are remote repos, not local paths
                if path_str.startswith(("http://", "https://")):
                    if obj_type == "repos":
                        self.manifest_remotes.append(path_str)
                    continue
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
        
        # Schema 2.0.0: remote.repos contains repo URLs
        for url in remote.get("repos", []):
            if url not in self.manifest_remotes:
                self.manifest_remotes.append(url)
        
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
        
        # Inherit properties from parents to children
        self._apply_inheritance()
        
        # Match overlays to base objects
        self._match_overlays()
        
        # Build dependency DAG and detect conflicts
        self._build_dependency_graph()
        self._detect_conflicts()
        
        if self.conflicts:
            conflict_msgs = [repr(c) for c in self.conflicts]
            logger.warning(f"Dependency conflicts detected: {conflict_msgs}")
        
        # Check for deprecated objects
        self._check_deprecations()
        
        # Check for missing peer dependencies
        self._check_peer_dependencies()
        
        if progress_callback:
            progress_callback("Complete", total, total)
        
        logger.info(f"Resolved {len(self.objects)} objects")
        return self.objects
    
    # ------------------------------------------------------------------
    # Remote repo crawling
    # ------------------------------------------------------------------

    def _crawl_remote_repos(self, urls: list[str]) -> dict[str, dict]:
        """
        Crawl remote repo URLs transitively, returning {url: repo_data}.
        
        Each repo JSON may contain a "repos" list pointing to sub-repos,
        which are also fetched. Already-visited URLs are skipped to avoid
        infinite loops.
        """
        import httpx

        visited: dict[str, dict] = {}
        queue = list(urls)
        while queue:
            url = queue.pop(0)
            if url in visited:
                continue
            try:
                # Try the URL as-is first
                resp = httpx.get(url, timeout=10, follow_redirects=True)
                # If not JSON, try appending /repo.json
                if resp.status_code != 200 or 'json' not in resp.headers.get('content-type', ''):
                    if not url.endswith('.json'):
                        alt_url = url.rstrip('/') + '/repo.json'
                        alt_resp = httpx.get(alt_url, timeout=10, follow_redirects=True)
                        if alt_resp.status_code == 200:
                            resp = alt_resp
                resp.raise_for_status()
                data = resp.json()
                visited[url] = data
                # Enqueue sub-repos for transitive crawling
                for sub_url in data.get("repos", []):
                    if sub_url not in visited:
                        queue.append(sub_url)
                logger.info(f"Crawled remote repo: {url}")
            except Exception as e:
                logger.warning(f"Failed to crawl remote repo {url}: {e}")
                visited[url] = {"repo_name": url, "_error": str(e)}
        return visited

    def _build_remote_objects(self) -> dict[str, dict]:
        """
        Build resolved-object-style entries for all crawled remote repos.
        
        Each remote repo becomes a first-class object in the cache with:
        - type: "repo"
        - children: gems/templates/projects/engines advertised by the repo
        - remotes: sub-repos listed in the repo
        
        Also creates entries for remotely-advertised objects (gems, etc.)
        that aren't locally resolved, so drill-down can display them.
        
        Returns:
            Dict of object_name -> resolved object dict
        """
        remote_objects: dict[str, dict] = {}
        
        for url, data in self._crawled_remotes.items():
            if data.get("_error"):
                repo_name = url
                remote_objects[repo_name] = {
                    "url": url,
                    "type": "repo",
                    "version": "",
                    "children": [],
                    "remotes": [],
                    "dependencies": [],
                    "status": "error",
                    "display_metadata": {"summary": f"Error: {data['_error']}"},
                }
                continue
            
            repo_name = data.get("repo_name", url)
            
            # Collect children: all advertised objects (gems, templates, etc.)
            children: list[str] = []
            for obj_type in ["engines", "projects", "gems", "templates"]:
                # Standard format: list of URLs
                for obj_url in data.get(obj_type, []):
                    if isinstance(obj_url, str):
                        # Extract name from URL: use parent path segment if
                        # the filename is generic (gem.json, template.json, etc.)
                        parts = obj_url.rstrip("/").split("/")
                        filename = parts[-1] if parts else obj_url
                        generic = {"gem.json", "template.json", "project.json",
                                   "engine.json", "repo.json"}
                        if filename.lower() in generic and len(parts) >= 2:
                            child_name = parts[-2]
                        else:
                            child_name = filename
                        # Create a remote object entry for this child
                        if child_name not in remote_objects and child_name not in self.objects:
                            remote_objects[child_name] = {
                                "url": obj_url,
                                "type": obj_type.rstrip("s"),
                                "version": "",
                                "children": [],
                                "remotes": [],
                                "dependencies": [],
                                "status": "remote",
                                "repo": repo_name,
                            }
                        children.append(child_name)
                
                # Legacy format: gems_data, projects_data, etc.
                for item in data.get(f"{obj_type}_data", []):
                    if isinstance(item, dict):
                        type_singular = obj_type.rstrip("s")
                        child_name = (
                            item.get(f"{type_singular}_name")
                            or item.get("name")
                            or item.get("display_name", "")
                        )
                        if child_name and child_name not in remote_objects and child_name not in self.objects:
                            remote_objects[child_name] = {
                                "url": item.get("repo_uri", item.get("origin_uri", "")),
                                "type": type_singular,
                                "version": item.get("version", ""),
                                "children": [],
                                "remotes": [],
                                "dependencies": [],
                                "status": "remote",
                                "repo": repo_name,
                                "display_metadata": {
                                    "display_name": item.get("display_name", ""),
                                    "summary": item.get("summary", ""),
                                } if item.get("display_name") or item.get("summary") else None,
                            }
                        if child_name:
                            children.append(child_name)
            
            # Collect remotes: sub-repos
            remotes: list[str] = []
            for sub_url in data.get("repos", []):
                sub_data = self._crawled_remotes.get(sub_url, {})
                sub_name = sub_data.get("repo_name", sub_url) if sub_data else sub_url
                remotes.append(sub_name)
            
            remote_objects[repo_name] = {
                "url": url,
                "type": "repo",
                "version": data.get("$schemaVersion", ""),
                "children": children,
                "remotes": remotes,
                "dependencies": [],
                "status": "remote",
                "display_metadata": {
                    "summary": data.get("summary", ""),
                    "display_name": data.get("repo_name", ""),
                } if data.get("summary") else None,
            }
        
        return remote_objects

    def get_missing_dependencies(self) -> list[tuple[str, ObjectNameVersion]]:
        """
        Find all dependencies that reference objects not present in the manifest.
        
        Returns:
            List of (requirer_name, dep_spec) tuples for each missing dep
        """
        missing: list[tuple[str, ObjectNameVersion]] = []
        for name, obj in self.objects.items():
            for dep_spec in obj.dependencies:
                candidate = self.objects.get(dep_spec.name)
                if candidate is None:
                    missing.append((name, dep_spec))
                elif not dep_spec.matches(candidate.version):
                    missing.append((name, dep_spec))
        return missing

    def get_missing_optional_dependencies(self) -> list[tuple[str, ObjectNameVersion]]:
        """
        Find optional dependencies not present in the manifest.

        These are not errors — they are suggestions for additional installs.

        Returns:
            List of (requirer_name, dep_spec) tuples for each missing optional dep
        """
        missing: list[tuple[str, ObjectNameVersion]] = []
        for name, obj in self.objects.items():
            for dep_spec in obj.optional_dependencies:
                candidate = self.objects.get(dep_spec.name)
                if candidate is None:
                    missing.append((name, dep_spec))
                elif not dep_spec.matches(candidate.version):
                    missing.append((name, dep_spec))
        return missing

    def auto_install_missing(
        self,
        store: "Store",
        confirm: bool = False,
        dry_run: bool = False,
        progress_callback: Optional[Callable[[str, int, int], None]] = None,
    ) -> list[dict]:
        """
        Automatically fetch and install missing dependencies from the store.

        This is the npm-style auto-install: after resolve() identifies missing
        deps, this method searches the store for matching remote objects,
        downloads them, registers them in the manifest, and re-resolves.

        Args:
            store: Store instance with refreshed remote catalog
            confirm: If False, raise with a list of what would be installed
                     (the CLI layer uses this to prompt the user or require --yes)
            dry_run: If True, return what would be installed without doing anything
            progress_callback: Optional callback(message, current, total)

        Returns:
            List of dicts describing installed objects:
            [{"name": ..., "version": ..., "type": ..., "path": ..., "source": ...}]

        Raises:
            ResolverError: If confirm=False and there are missing deps (contains
                           the list of missing deps for the caller to present)
        """
        from .store import Store, RemoteObject
        from .paths import get_default_path_for_type
        from .models import ObjectType

        missing = self.get_missing_dependencies()
        if not missing:
            return []

        # Deduplicate: same dep might be required by multiple objects
        unique_missing: dict[str, ObjectNameVersion] = {}
        for _requirer, dep_spec in missing:
            if dep_spec.name not in unique_missing:
                unique_missing[dep_spec.name] = dep_spec

        # Search the store for each missing dep
        install_plan: list[tuple[ObjectNameVersion, RemoteObject]] = []
        not_found: list[str] = []

        for dep_name, dep_spec in unique_missing.items():
            # Search across all object types
            candidates = store.search(dep_name)

            # Find exact name match with compatible version
            best: RemoteObject | None = None
            for candidate in candidates:
                if candidate.name == dep_name:
                    if dep_spec.matches(candidate.version):
                        if best is None or store._is_newer_version(
                            candidate.version, best.version
                        ):
                            best = candidate

            if best:
                install_plan.append((dep_spec, best))
            else:
                not_found.append(dep_name)

        if not install_plan and not_found:
            logger.warning(
                f"Could not find remote objects for: {', '.join(not_found)}"
            )
            return []

        # Build the install summary
        plan_summary = [
            {
                "name": remote.name,
                "version": remote.version,
                "type": remote.object_type.value,
                "source": remote.effective_source_control_url or remote.download_url or remote.url,
            }
            for _spec, remote in install_plan
        ]

        if dry_run:
            return plan_summary

        if not confirm:
            raise ResolverError(
                f"Missing {len(install_plan)} dependencies. "
                f"Use --yes to auto-install or --dry-run to preview.\n"
                + "\n".join(
                    f"  {p['name']}@{p['version']} ({p['type']})"
                    for p in plan_summary
                )
            )

        # Actually download and register each missing dep
        installed: list[dict] = []
        total = len(install_plan)

        for idx, (dep_spec, remote) in enumerate(install_plan, 1):
            if progress_callback:
                progress_callback(
                    f"Installing {remote.name}@{remote.version}", idx, total
                )

            target_path = get_default_path_for_type(remote.object_type)

            try:
                download_path = store.download_sync(
                    remote, target_path, expected_sha256=remote.source_sha256
                )
            except Exception as e:
                logger.error(f"Failed to download {remote.name}: {e}")
                continue

            # Register in the manifest
            self._add_to_manifest(download_path, remote.object_type)

            installed.append({
                "name": remote.name,
                "version": remote.version,
                "type": remote.object_type.value,
                "path": str(download_path),
                "source": remote.effective_source_control_url or remote.download_url or "",
            })

        if installed:
            logger.info(f"Auto-installed {len(installed)} dependencies")

        return installed

    def _add_to_manifest(self, obj_path: Path, obj_type: "ObjectType") -> None:
        """Register a downloaded object in the manifest file."""
        import json as _json

        if not self.manifest_path.exists():
            return

        with open(self.manifest_path, "r") as f:
            manifest_data = _json.load(f)

        local = manifest_data.setdefault("local", {})
        type_key = obj_type.value + "s"
        type_list = local.setdefault(type_key, [])

        path_str = obj_path.resolve().as_posix()
        # Avoid duplicates
        resolved_existing = {Path(p).resolve().as_posix() for p in type_list}
        if path_str not in resolved_existing:
            type_list.append(path_str)
            with open(self.manifest_path, "w") as f:
                _json.dump(manifest_data, f, indent=2)
            logger.info(f"Registered {obj_type.value}: {obj_path.name}")
    
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
        # Schema 2.0.0: type_dict.dependent with type keys: {"gems": ["org.o3de.gem.a>=1.0.0"]}
        # Legacy: root-level "dependencies" flat list: ["GemA", "GemB"]
        
        # Schema 2.0.0: dependent can be inside the type dict (e.g., data["gem"]["dependent"])
        type_key = expected_type.value
        type_data = data.get(type_key, {})
        dependent = type_data.get("dependent", {}) if isinstance(type_data, dict) else {}
        
        # Also check root level (some formats put it there)
        if not dependent:
            dependent = data.get("dependent", {})
        
        if isinstance(dependent, dict):
            for dep_list in dependent.values():
                if isinstance(dep_list, list):
                    for dep in dep_list:
                        resolved.dependencies.append(ObjectNameVersion(dep))
        
        # Also check inside type dict for "dependencies" (Schema 2.0.0 alt)
        type_deps = type_data.get("dependencies", {}) if isinstance(type_data, dict) else {}
        if isinstance(type_deps, dict):
            for dep_list in type_deps.values():
                if isinstance(dep_list, list):
                    for dep in dep_list:
                        resolved.dependencies.append(ObjectNameVersion(dep))
        
        # Also check legacy format (flat list at root)
        legacy_deps = data.get("dependencies", [])
        if isinstance(legacy_deps, list):
            for dep in legacy_deps:
                if isinstance(dep, str):
                    resolved.dependencies.append(ObjectNameVersion(dep))
        
        # Parse optional_dependent (nice-to-have deps, not required)
        optional_dep = type_data.get("optional_dependent", {}) if isinstance(type_data, dict) else {}
        if not optional_dep:
            optional_dep = data.get("optional_dependent", {})
        if isinstance(optional_dep, dict):
            for dep_list in optional_dep.values():
                if isinstance(dep_list, list):
                    for dep in dep_list:
                        resolved.optional_dependencies.append(ObjectNameVersion(dep))
        
        # Parse peer_dependent (must be provided by consumer)
        peer_dep = type_data.get("peer_dependent", {}) if isinstance(type_data, dict) else {}
        if not peer_dep:
            peer_dep = data.get("peer_dependent", {})
        if isinstance(peer_dep, dict):
            for dep_list in peer_dep.values():
                if isinstance(dep_list, list):
                    for dep in dep_list:
                        resolved.peer_dependencies.append(ObjectNameVersion(dep))
        
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
    
    # Type-key → expected JSON filename inside the registered directory
    _TYPE_JSON = {
        "engines": "engine.json",
        "projects": "project.json",
        "gems": "gem.json",
        "templates": "template.json",
        "repos": "repo.json",
        "overlays": "overlay.json",
    }

    def _sanitize_manifest(self, local: dict) -> bool:
        """Deduplicate entries and validate type assignments in *local*.

        Returns True if the manifest was modified and should be saved.
        """
        dirty = False
        all_type_keys = list(self._TYPE_JSON.keys())

        for type_key in all_type_keys:
            entries = local.get(type_key, [])
            if not entries:
                continue

            # 1. Deduplicate (preserve first occurrence, compare resolved)
            seen: set[str] = set()
            deduped: list[str] = []
            for p in entries:
                resolved = str(Path(p).resolve())
                if resolved in seen:
                    logger.warning(f"Removing duplicate {type_key} entry: {p}")
                    dirty = True
                    continue
                seen.add(resolved)
                deduped.append(p)

            # 2. Validate: the registered path should contain the expected
            #    JSON file for this type list.  If it is in the wrong list,
            #    move it to the correct one.
            expected_json = self._TYPE_JSON[type_key]
            keep: list[str] = []
            for p in deduped:
                obj_dir = Path(p).resolve()
                if obj_dir.suffix == ".json":
                    obj_dir = obj_dir.parent

                if not obj_dir.is_dir():
                    keep.append(p)   # leave stale-path removal to existing code
                    continue

                if (obj_dir / expected_json).exists():
                    keep.append(p)
                    continue

                # Wrong list — figure out the correct one
                moved = False
                for correct_key, correct_json in self._TYPE_JSON.items():
                    if correct_key == type_key:
                        continue
                    if (obj_dir / correct_json).exists():
                        # Move to correct list
                        correct_list = local.setdefault(correct_key, [])
                        if p not in correct_list:
                            correct_list.append(p)
                        logger.warning(
                            f"Moved {p} from {type_key} to {correct_key} "
                            f"(found {correct_json})"
                        )
                        dirty = True
                        moved = True
                        break

                if not moved:
                    # No matching JSON found at all — keep it (let stale
                    # path removal handle it if dir doesn't exist later)
                    keep.append(p)

            if keep != entries:
                local[type_key] = keep
                dirty = True

        return dirty

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
    
    def _build_dependency_graph(self) -> None:
        """
        Build the full dependency DAG with transitive dependencies.
        
        For each object, compute the full list of transitive dependencies
        (direct deps + deps of deps, ...) and pin them with resolved versions.
        """
        self.dependency_graph = {}
        self.locked_dependencies = {}
        
        for name, obj in self.objects.items():
            # Walk the full transitive dependency tree
            visited: set[str] = set()
            pinned: list[tuple[str, str]] = []
            
            self._walk_dependencies(obj, visited, pinned)
            
            self.dependency_graph[name] = pinned
            
            # Build locked deps entry (pinned transitive versions)
            if pinned:
                self.locked_dependencies[name] = {
                    dep_name: dep_version for dep_name, dep_version in pinned
                }
    
    def _walk_dependencies(
        self,
        obj: ResolvedObject,
        visited: set[str],
        pinned: list[tuple[str, str]],
    ) -> None:
        """Recursively walk dependencies, collecting transitive pins."""
        for dep_spec in obj.dependencies:
            if dep_spec.name in visited:
                continue
            visited.add(dep_spec.name)
            
            # Find matching resolved object
            candidate = self.objects.get(dep_spec.name)
            if candidate and dep_spec.matches(candidate.version):
                pinned.append((candidate.name, candidate.version))
                # Recurse into transitive deps
                self._walk_dependencies(candidate, visited, pinned)

        # Also resolve optional dependencies if they happen to be present locally.
        # Missing optional deps are NOT errors — they are just skipped.
        for dep_spec in obj.optional_dependencies:
            if dep_spec.name in visited:
                continue
            visited.add(dep_spec.name)

            candidate = self.objects.get(dep_spec.name)
            if candidate and dep_spec.matches(candidate.version):
                pinned.append((candidate.name, candidate.version))
                self._walk_dependencies(candidate, visited, pinned)
    
    def _detect_conflicts(self) -> None:
        """
        Detect version conflicts in the dependency graph.
        
        A conflict occurs when two objects require different incompatible
        versions of the same dependency (e.g., A wants X>=2.0.0 and B wants X<2.0.0).
        """
        self.conflicts = []
        
        # Collect all constraints per dependency: dep_name -> [(requirer, spec)]
        all_constraints: dict[str, list[tuple[str, ObjectNameVersion]]] = {}
        
        for name, obj in self.objects.items():
            for dep_spec in obj.dependencies:
                if dep_spec.name not in all_constraints:
                    all_constraints[dep_spec.name] = []
                all_constraints[dep_spec.name].append((name, dep_spec))
        
        # Check each dependency that has multiple requirers
        for dep_name, constraints in all_constraints.items():
            if len(constraints) < 2:
                continue
            
            resolved = self.objects.get(dep_name)
            resolved_version = resolved.version if resolved else None
            
            # Check all pairs for incompatibility
            for i in range(len(constraints)):
                for j in range(i + 1, len(constraints)):
                    requirer_a, spec_a = constraints[i]
                    requirer_b, spec_b = constraints[j]
                    
                    # Both must have version constraints to conflict
                    if not spec_a.specifier and not spec_b.specifier:
                        continue
                    
                    # Check if there's any version that satisfies both
                    if resolved_version:
                        a_satisfied = spec_a.matches(resolved_version)
                        b_satisfied = spec_b.matches(resolved_version)
                        
                        if not (a_satisfied and b_satisfied):
                            self.conflicts.append(DependencyConflict(
                                dependency_name=dep_name,
                                requirer_a=requirer_a,
                                constraint_a=str(spec_a.specifier) or "*",
                                requirer_b=requirer_b,
                                constraint_b=str(spec_b.specifier) or "*",
                                resolved_version=resolved_version,
                            ))
    
    def _check_deprecations(self) -> None:
        """Emit warnings for any resolved objects with deprecated status."""
        for name, obj in self.objects.items():
            # Schema 2.0.0: {type: {deprecated: {message, replacement}}}
            type_key = obj.object_type.value
            type_data = obj.data.get(type_key, {})
            deprecated = type_data.get("deprecated")
            
            # Legacy: deprecated at root level  
            if not deprecated:
                deprecated = obj.data.get("deprecated")
            
            if deprecated:
                if isinstance(deprecated, dict):
                    msg = deprecated.get("message", "This object is deprecated.")
                    replacement = deprecated.get("replacement", "")
                    warning = f"DEPRECATED: {name} — {msg}"
                    if replacement:
                        warning += f" Use {replacement} instead."
                else:
                    warning = f"DEPRECATED: {name} — {deprecated}"
                logger.warning(warning)
    
    def _check_peer_dependencies(self) -> None:
        """Emit warnings for missing peer dependencies."""
        for name, obj in self.objects.items():
            for peer_spec in obj.peer_dependencies:
                candidate = self.objects.get(peer_spec.name)
                if candidate is None:
                    logger.warning(
                        f"PEER DEPENDENCY: {name} requires peer '{peer_spec}' "
                        f"which is not installed"
                    )
                elif not peer_spec.matches(candidate.version):
                    logger.warning(
                        f"PEER DEPENDENCY: {name} requires peer '{peer_spec}' "
                        f"but found version {candidate.version}"
                    )
    
    # ------------------------------------------------------------------
    # Property inheritance
    # ------------------------------------------------------------------

    # Properties that a child inherits from its parent when not defined.
    # Each entry is the JSON key in the object's data dict.
    INHERITABLE_PROPERTIES = ("origin", "licenses", "source_control", "documentation")

    def _apply_inheritance(self) -> None:
        """
        Inherit properties from parent objects to children that lack them.

        Inheritable properties (origin, licenses, source_control, documentation)
        propagate down the parent chain.  A child that already defines a property
        keeps its own value; only missing properties are filled in.

        After this method runs, every ResolvedObject's ``data`` dict contains
        the effective value for each inheritable property, and
        ``inherited_from`` records the parent name it came from (if any).
        """
        for obj in self.objects.values():
            if obj.parent is None:
                continue
            self._inherit_from_parent(obj)

    def _inherit_from_parent(self, obj: ResolvedObject) -> None:
        """
        Walk up the parent chain and inherit missing properties.

        For each inheritable property, the first ancestor that defines it
        wins.  The property value is **copied** into ``obj.data`` so that
        downstream consumers see a fully-resolved object, and the parent's
        name is recorded in ``obj.inherited_from``.
        """
        for prop in self.INHERITABLE_PROPERTIES:
            # Check if the child already has this property
            if self._has_property(obj, prop):
                continue

            # Walk parent chain until we find a provider
            ancestor = obj.parent
            while ancestor is not None:
                if self._has_property(ancestor, prop):
                    # Copy value into child's data
                    value = self._get_property(ancestor, prop)
                    obj.data[prop] = value
                    # Track the *original* source – if the ancestor itself
                    # inherited this property, record its ultimate origin
                    # rather than the relay ancestor.
                    source = ancestor.inherited_from.get(prop, ancestor.name)
                    obj.inherited_from[prop] = source
                    logger.debug(
                        f"Inherited '{prop}' for {obj.name} from {source}"
                    )
                    break
                ancestor = ancestor.parent

    @staticmethod
    def _has_property(obj: ResolvedObject, prop: str) -> bool:
        """Check if an object defines a property (non-empty)."""
        val = obj.data.get(prop)
        if val is None:
            return False
        # An empty dict/list/string counts as not having the property
        if isinstance(val, (dict, list, str)) and not val:
            return False
        return True

    @staticmethod
    def _get_property(obj: ResolvedObject, prop: str) -> Any:
        """
        Get a deep copy of a property value from an object.

        Uses deep copy to prevent mutations in one object from affecting
        another.
        """
        import copy
        return copy.deepcopy(obj.data.get(prop))

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
        - locked_dependencies: pinned transitive dependency versions
        - conflicts: detected version conflicts (if any)
        
        In dry-run mode, computes everything but skips writing to disk.
        
        Returns:
            Path to saved file (even in dry-run mode)
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
        
        # Crawl all remote repo URLs discovered from manifest and objects
        all_remote_urls: set[str] = set(self.manifest_remotes)
        for name, obj in self.objects.items():
            obj_remote = obj.data.get("remote", {})
            if isinstance(obj_remote, dict):
                for url in obj_remote.get("repos", []):
                    all_remote_urls.add(url)
        
        # Pre-crawl and build remote objects
        if all_remote_urls:
            crawled = self._crawl_remote_repos(list(all_remote_urls))
            self._crawled_remotes.update(crawled)
        remote_objects = self._build_remote_objects()
        
        # Build URL->repo_name mapping for resolving object remotes
        url_to_name: dict[str, str] = {}
        for url, data in self._crawled_remotes.items():
            if not data.get("_error"):
                url_to_name[url] = data.get("repo_name", url)
            else:
                url_to_name[url] = url
        
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
                "optional_dependencies": [str(d) for d in obj.optional_dependencies] or None,
                "peer_dependencies": [str(d) for d in obj.peer_dependencies] or None,
                "all_dependencies": [
                    {"name": dn, "version": dv}
                    for dn, dv in self.dependency_graph.get(name, [])
                ] or None,
                "dependents": dependents_map.get(name, []),
                "overlays": [o.name for o in obj.overlays],
                "parent": obj.parent.name if obj.parent else None,
                "parents": parents,  # Full ancestry: [{name, path}, ...] from immediate parent to root
                "display_metadata": display_metadata if display_metadata else None,
                "git_info": git_info if git_info else None,
                "releases": release_versions if release_versions else None,
                # Inheritable properties (effective values after inheritance)
                "origin": obj.data.get("origin") or None,
                "licenses": obj.data.get("licenses") or None,
                "source_control": obj.data.get("source_control") or None,
                "documentation": obj.data.get("documentation") or None,
                # Which properties were inherited and from whom
                "inherited_from": obj.inherited_from if obj.inherited_from else None,
            }

            # Compute all_children: transitive closure of children
            if obj.children:
                ac_list: list[dict] = []
                ac_seen: set[str] = set()
                ac_q = [c.name for c in obj.children]
                while ac_q:
                    cn = ac_q.pop(0)
                    if cn in ac_seen:
                        continue
                    ac_seen.add(cn)
                    cobj = self.objects.get(cn)
                    ctype = cobj.object_type.value if cobj else ""
                    ac_list.append({"name": cn, "type": ctype})
                    if cobj:
                        for cc in cobj.children:
                            if cc.name not in ac_seen:
                                ac_q.append(cc.name)
                resolved_data["objects"][name]["all_children"] = ac_list or None

            # Build remotes for this object (list of repo names, like children)
            obj_remote = obj.data.get("remote", {})
            remote_names: list[str] = []
            if isinstance(obj_remote, dict):
                for url in obj_remote.get("repos", []):
                    rname = url_to_name.get(url, url)
                    if rname not in remote_names:
                        remote_names.append(rname)
            # Root objects also get manifest-level remotes
            if not obj.parent:
                for url in self.manifest_remotes:
                    rname = url_to_name.get(url, url)
                    if rname not in remote_names:
                        remote_names.append(rname)
            if remote_names:
                resolved_data["objects"][name]["remotes"] = remote_names

            # all_remotes = transitive closure through remote chains
            # Walk: object -> remotes -> remotes' remotes, etc.
            if remote_names:
                all_remote_set: list[dict] = []
                seen: set[str] = set()
                queue = list(remote_names)
                while queue:
                    rn = queue.pop(0)
                    if rn in seen:
                        continue
                    seen.add(rn)
                    robj = remote_objects.get(rn, {})
                    rtype = robj.get("type", "repo")
                    all_remote_set.append({"name": rn, "type": rtype})
                    # Add children of this remote (advertised objects)
                    for child in robj.get("children", []):
                        if child not in seen:
                            cobj = remote_objects.get(child, {})
                            ctype = cobj.get("type", "")
                            all_remote_set.append({"name": child, "type": ctype})
                            seen.add(child)
                    # Enqueue sub-remotes for transitive walk
                    for sub in robj.get("remotes", []):
                        if sub not in seen:
                            queue.append(sub)
                if all_remote_set:
                    resolved_data["objects"][name]["all_remotes"] = all_remote_set
            
            # Add to type list
            type_key = obj.object_type.value + "s"
            if type_key in resolved_data:
                resolved_data[type_key].append({
                    "name": name,
                    "path": obj.path.as_posix(),
                    "version": obj.version,
                })
        
        # Add remote objects to the cache (repos and their advertised objects)
        for rname, rdata in remote_objects.items():
            if rname not in resolved_data["objects"]:
                resolved_data["objects"][rname] = rdata
                # Add repos to the repos type list
                if rdata.get("type") == "repo":
                    resolved_data["repos"].append({
                        "name": rname,
                        "url": rdata.get("url", ""),
                        "version": rdata.get("version", ""),
                    })
        
        # Create manifest root entry — the tree root
        manifest_name = "o3de_manifest"
        # Root children = all root-level objects (no parent)
        root_children = [n for n, o in self.objects.items() if o.parent is None]
        # Root remotes = manifest-level repo names
        root_remotes = [url_to_name.get(u, u) for u in self.manifest_remotes]
        
        # Compute all_children (transitive closure) for manifest root
        root_all_children: list[dict] = []
        ac_seen: set[str] = set()
        ac_queue = list(root_children)
        while ac_queue:
            cn = ac_queue.pop(0)
            if cn in ac_seen:
                continue
            ac_seen.add(cn)
            cobj = self.objects.get(cn)
            ctype = cobj.object_type.value if cobj else ""
            root_all_children.append({"name": cn, "type": ctype})
            if cobj:
                for cc in cobj.children:
                    if cc.name not in ac_seen:
                        ac_queue.append(cc.name)
        
        # Compute all_remotes for manifest root:
        # Aggregate from manifest's own remotes PLUS all descendants' remotes
        all_obj_remote_names: set[str] = set(root_remotes)
        for name in resolved_data["objects"]:
            obj_remotes = resolved_data["objects"][name].get("remotes", [])
            for rn in obj_remotes:
                all_obj_remote_names.add(rn)
        
        root_all_remotes: list[dict] = []
        if all_obj_remote_names:
            seen: set[str] = set()
            queue = list(all_obj_remote_names)
            while queue:
                rn = queue.pop(0)
                if rn in seen:
                    continue
                seen.add(rn)
                robj = remote_objects.get(rn, {})
                rtype = robj.get("type", "repo")
                root_all_remotes.append({"name": rn, "type": rtype})
                for child in robj.get("children", []):
                    if child not in seen:
                        cobj = remote_objects.get(child, {})
                        root_all_remotes.append({"name": child, "type": cobj.get("type", "")})
                        seen.add(child)
                for sub in robj.get("remotes", []):
                    if sub not in seen:
                        queue.append(sub)
        
        resolved_data["manifest_root"] = {
            "name": manifest_name,
            "path": self.manifest_path.as_posix(),
            "children": root_children,
            "all_children": root_all_children if root_all_children else None,
            "remotes": root_remotes,
            "all_remotes": root_all_remotes if root_all_remotes else None,
        }
        
        # Include locked transitive dependencies for reproducibility
        if self.locked_dependencies:
            resolved_data["locked_dependencies"] = self.locked_dependencies
        
        # Include detected conflicts as warnings
        if self.conflicts:
            resolved_data["conflicts"] = [
                {
                    "dependency": c.dependency_name,
                    "requirer_a": c.requirer_a,
                    "constraint_a": c.constraint_a,
                    "requirer_b": c.requirer_b,
                    "constraint_b": c.constraint_b,
                    "resolved_version": c.resolved_version,
                }
                for c in self.conflicts
            ]
        
        if self.dry_run:
            logger.info(f"Dry-run: would save resolved manifest to {self.resolved_path}")
            return self.resolved_path
        
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
    dry_run: bool = False,
    progress_callback: Optional[Callable[[str, int, int], None]] = None,
) -> Resolver:
    """
    Convenience function to resolve the manifest.
    
    Args:
        manifest_path: Path to manifest (default: ~/.o3de/o3de_manifest.json)
        save: Whether to save resolved manifest
        dry_run: If True, resolve but don't write to disk
        progress_callback: Progress callback
    
    Returns:
        Resolver with resolved objects
    """
    resolver = Resolver(manifest_path, dry_run=dry_run)
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
