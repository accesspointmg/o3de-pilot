# O3DE Pilot GUI - Background Loader Thread
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Background thread for loading O3DE objects without blocking the GUI.

Moves all heavy I/O (manifest resolution, remote repo fetching,
GitHub release checks) off the main thread so the splash spinner
animates smoothly.
"""

from PySide6.QtCore import QThread, Signal


class LoaderThread(QThread):
    """
    Loads objects in a background thread.

    Signals
    -------
    statusChanged(str, str)
        Emitted with (status_text, detail_text) for progress updates.
    objectsReady(list, object, int, int)
        Emitted when loading is complete with
        (list[ObjectInfo], Store | None, local_count, remote_count).
    loadError(str)
        Emitted if an unrecoverable error occurs.
    """

    statusChanged = Signal(str, str)
    objectsReady = Signal(list, object, int, int, dict)
    loadError = Signal(str)

    def __init__(self, *, offline: bool = False, parent=None):
        super().__init__(parent)
        self._offline = offline

    def run(self):  # noqa: C901
        try:
            from o3de_cli.core import get_manifest_path, Store
            from o3de_cli.core.resolver import load_resolved_manifest
            from o3de_cli.core.git_utils import get_github_releases, get_local_git_upstream
            from .object_info import ObjectInfo, ObjectOrigin, ObjectType
            import json

            self.statusChanged.emit("Locating manifest...", "")
            manifest_path = get_manifest_path()
            if not manifest_path.exists():
                self.objectsReady.emit([], None, 0, 0)
                return

            objects: list[ObjectInfo] = []
            local_keys: set[str] = set()
            local_count = 0
            remote_count = 0
            store = None

            # ----------------------------------------------------------
            # 1. Local objects from cached resolved manifest
            # ----------------------------------------------------------
            self.statusChanged.emit("Resolving local objects...", "")
            resolved_data = load_resolved_manifest()
            objects_dict = resolved_data.get("objects", {})
            total_local = sum(
                1 for v in objects_dict.values() if v.get("status") != "remote"
            )

            for name, obj_data in objects_dict.items():
                if obj_data.get("status") == "remote":
                    continue
                info = ObjectInfo.from_resolved_dict(name, obj_data)
                objects.append(info)
                local_keys.add(f"{info.object_type.value}:{info.name}")
                local_count += 1
                if local_count % 20 == 0:
                    self.statusChanged.emit(
                        "Loading local objects...",
                        f"{local_count} / {total_local}",
                    )

            # ----------------------------------------------------------
            # 2. Remote objects from Store (skipped in offline mode)
            # ----------------------------------------------------------
            if not self._offline:
                try:
                    with open(manifest_path) as f:
                        manifest_data = json.load(f)

                    repo_urls = manifest_data.get("repos", [])
                    if not repo_urls:
                        remote_section = manifest_data.get("remote", {})
                        repo_urls = remote_section.get("repos", [])

                    if repo_urls:
                        self.statusChanged.emit(
                            "Fetching remote repos...",
                            f"{len(repo_urls)} repo(s)",
                        )
                        store = Store()
                        remote_count = store.refresh_sync(repo_urls)

                        for remote_obj in store.objects.values():
                            if remote_obj.object_type.value == "repo":
                                continue
                            remote_key = (
                                f"{remote_obj.object_type.value}:{remote_obj.name}"
                            )
                            if remote_key in local_keys:
                                continue
                            info = ObjectInfo.from_remote_object(remote_obj)
                            info.available_versions = store.get_versions(
                                remote_obj.object_type, remote_obj.name
                            )
                            objects.append(info)

                        # Merge store versions into local objects
                        for info in objects:
                            if info.origin == ObjectOrigin.LOCAL and store:
                                versions = store.get_versions(
                                    info.object_type, info.name
                                )
                                if versions:
                                    info.available_versions = versions

                except Exception:
                    import traceback

                    traceback.print_exc()
                    # Continue with local objects even if remote fails

            # ----------------------------------------------------------
            # 3. GitHub releases (skipped in offline mode) — parallel
            # ----------------------------------------------------------
            if not self._offline:
                self.statusChanged.emit("Fetching GitHub releases...", "")
                from concurrent.futures import ThreadPoolExecutor, as_completed

                engine_releases_by_path: dict[str, list[str]] = {}
                for info in objects:
                    if (
                        info.origin == ObjectOrigin.LOCAL
                        and info.object_type == ObjectType.ENGINE
                    ):
                        if info.path and info.json_releases:
                            engine_path = (
                                str(info.path).replace("\\", "/").rstrip("/")
                            )
                            engine_releases_by_path[engine_path] = info.json_releases

                # Collect local objects that need release checks
                local_objects = [
                    info for info in objects if info.origin == ObjectOrigin.LOCAL
                ]

                # Phase 3a: Determine GitHub URL for each object.
                # Prefer repository_url/origin_url (already known from manifest).
                # Only call get_local_git_upstream for objects without a known URL.
                obj_git_urls: dict[int, str] = {}  # index -> git_url
                unique_git_urls: set[str] = set()
                needs_upstream: list[tuple[int, str]] = []  # (idx, path)

                for idx, info in enumerate(local_objects):
                    known_url = info.repository_url or info.origin_url
                    if known_url and "github.com" in known_url:
                        obj_git_urls[idx] = known_url
                        unique_git_urls.add(known_url)
                    elif info.path:
                        needs_upstream.append((idx, str(info.path)))

                # Only resolve git upstreams for objects without a known URL
                if needs_upstream:
                    self.statusChanged.emit(
                        "Resolving git upstreams...",
                        f"{len(needs_upstream)} objects",
                    )
                    unique_paths = {p for _, p in needs_upstream}
                    path_to_upstream: dict[str, str | None] = {}
                    with ThreadPoolExecutor(max_workers=32) as executor:
                        future_to_path = {
                            executor.submit(get_local_git_upstream, p): p
                            for p in unique_paths
                        }
                        for future in as_completed(future_to_path):
                            path = future_to_path[future]
                            try:
                                path_to_upstream[path] = future.result()
                            except Exception:
                                path_to_upstream[path] = None

                    for idx, path in needs_upstream:
                        upstream = path_to_upstream.get(path)
                        if upstream and "github.com" in upstream:
                            obj_git_urls[idx] = upstream
                            unique_git_urls.add(upstream)

                # Phase 3c: Fetch releases for unique URLs in parallel
                self.statusChanged.emit(
                    "Fetching GitHub releases...",
                    f"{len(unique_git_urls)} repos",
                )
                url_to_releases: dict[str, list[str]] = {}
                with ThreadPoolExecutor(max_workers=16) as executor:
                    future_to_url = {
                        executor.submit(get_github_releases, url): url
                        for url in unique_git_urls
                    }
                    done_count = 0
                    for future in as_completed(future_to_url):
                        url = future_to_url[future]
                        done_count += 1
                        if done_count % 10 == 0:
                            self.statusChanged.emit(
                                "Fetching GitHub releases...",
                                f"{done_count}/{len(unique_git_urls)}",
                            )
                        try:
                            url_to_releases[url] = future.result()
                        except Exception:
                            url_to_releases[url] = []

                # Phase 3d: Map release data back to objects
                for idx, git_url in obj_git_urls.items():
                    info = local_objects[idx]
                    github_releases = url_to_releases.get(git_url, [])
                    if github_releases:
                        json_versions = set(info.json_releases)
                        if (
                            not json_versions
                            and info.path
                            and info.object_type != ObjectType.ENGINE
                        ):
                            obj_path = str(info.path).replace("\\", "/")
                            for ep, er in engine_releases_by_path.items():
                                if obj_path.startswith(ep + "/"):
                                    json_versions = set(er)
                                    info.json_releases = er.copy()
                                    break
                        github_only = [
                            v
                            for v in github_releases
                            if v not in json_versions
                        ]
                        info.github_only_versions = github_only
                        all_versions = list(github_releases)
                        for v in info.json_releases:
                            if v not in all_versions:
                                all_versions.append(v)
                        info.available_versions = all_versions

            # ----------------------------------------------------------
            # Done
            # ----------------------------------------------------------
            self.statusChanged.emit(
                "Finishing up...",
                f"{local_count} local + {remote_count} remote objects",
            )
            self.objectsReady.emit(objects, store, local_count, remote_count, resolved_data)

        except Exception as e:
            import traceback

            traceback.print_exc()
            self.loadError.emit(str(e))
