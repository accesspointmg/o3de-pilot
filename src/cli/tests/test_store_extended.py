# O3DE Pilot - Extended Store Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Extended tests for o3de_pilot.core.store module — covers fetch, refresh, search, download."""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import httpx

from o3de_pilot.core.store import (
    Cache,
    RemoteObject,
    Store,
    StoreError,
    FetchError,
    IntegrityError,
    compute_sha256,
    verify_integrity,
)
from o3de_pilot.core.models import ObjectType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_store(tmp_path):
    """Create a Store with a temporary cache."""
    return Store(cache=Cache(tmp_path / "cache"))


def _make_remote_obj(name="org.o3de.gem.test", version="1.0.0", **kw):
    return RemoteObject(
        url=kw.pop("url", f"https://example.com/{name}.json"),
        object_type=kw.pop("object_type", ObjectType.GEM),
        name=name,
        version=version,
        **kw,
    )


# ---------------------------------------------------------------------------
# TestFetchJsonSync
# ---------------------------------------------------------------------------

class TestFetchJsonSync:
    """Test synchronous JSON fetching with cache."""

    def test_cache_hit_returns_cached(self, tmp_path):
        store = _make_store(tmp_path)
        url = "https://example.com/repo.json"
        expected = {"repo": {"name": "test"}}
        store.cache.put(url, expected)

        result = store.fetch_json_sync(url)
        assert result == expected

    def test_cache_miss_fetches_http(self, tmp_path):
        store = _make_store(tmp_path)
        url = "https://example.com/repo.json"
        payload = {"repo": {"name": "remote"}}

        mock_response = MagicMock()
        mock_response.json.return_value = payload
        mock_response.headers = {"etag": '"abc"'}
        mock_response.raise_for_status = MagicMock()

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.return_value = mock_response

        with patch("o3de_pilot.core.store.httpx.Client", return_value=mock_client):
            result = store.fetch_json_sync(url, use_cache=False)

        assert result == payload
        # Should be cached now
        assert store.cache.get(url) == payload

    def test_http_error_falls_back_to_stale_cache(self, tmp_path):
        store = _make_store(tmp_path)
        url = "https://example.com/stale.json"
        stale_data = {"stale": True}
        store.cache.put(url, stale_data)
        # Force stale
        import hashlib
        cache_path = store.cache.cache_dir / hashlib.sha256(url.encode()).hexdigest()
        meta_path = cache_path / "metadata.json"
        meta = json.loads(meta_path.read_text())
        meta["cached_at"] = "1970-01-01T00:00:00+00:00"
        meta_path.write_text(json.dumps(meta))

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.HTTPError("timeout")

        with patch("o3de_pilot.core.store.httpx.Client", return_value=mock_client):
            result = store.fetch_json_sync(url)

        assert result == stale_data

    def test_http_error_no_cache_raises(self, tmp_path):
        store = _make_store(tmp_path)
        url = "https://example.com/nope.json"

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.get.side_effect = httpx.HTTPError("timeout")

        with patch("o3de_pilot.core.store.httpx.Client", return_value=mock_client):
            with pytest.raises(FetchError, match="Failed to fetch"):
                store.fetch_json_sync(url, use_cache=False)


# ---------------------------------------------------------------------------
# TestRefreshSync
# ---------------------------------------------------------------------------

class TestRefreshSync:
    """Test synchronous store refresh."""

    def test_single_repo(self, tmp_path):
        store = _make_store(tmp_path)
        repo_data = {
            "repo": {"name": "org.test.repo.main"},
            "$schemaVersion": "2.0.0",
            "gems": [],
        }
        with patch.object(store, "fetch_json_sync", return_value=repo_data):
            count = store.refresh_sync(["https://example.com/repo.json"])
        assert count >= 0

    def test_multi_hop_with_dedup(self, tmp_path):
        store = _make_store(tmp_path)
        call_count = 0

        def mock_fetch(url, **kw):
            nonlocal call_count
            call_count += 1
            if "repo.json" in url:
                return {
                    "repo": {"name": "org.test.repo.root"},
                    "$schemaVersion": "2.0.0",
                    "gems": ["https://example.com/gem.json"],
                }
            return {
                "gem": {"name": "org.test.gem.leaf", "version": "1.0.0"},
                "$schemaVersion": "2.0.0",
            }

        with patch.object(store, "fetch_json_sync", side_effect=mock_fetch):
            store.refresh_sync(["https://example.com/repo.json"])

        assert call_count == 2  # repo + gem

    def test_cycle_detection(self, tmp_path):
        store = _make_store(tmp_path)

        def mock_fetch(url, **kw):
            return {
                "repo": {"name": "org.test.repo.cycle"},
                "$schemaVersion": "2.0.0",
                "repos": ["https://example.com/repo.json"],  # cycle back
            }

        with patch.object(store, "fetch_json_sync", side_effect=mock_fetch):
            count = store.refresh_sync(["https://example.com/repo.json"])
        # Should not infinite loop
        assert count >= 0

    def test_fetch_error_skips(self, tmp_path):
        store = _make_store(tmp_path)

        def mock_fetch(url, **kw):
            raise FetchError("down")

        with patch.object(store, "fetch_json_sync", side_effect=mock_fetch):
            count = store.refresh_sync(["https://example.com/repo.json"])
        assert count == 0

    def test_progress_callback(self, tmp_path):
        store = _make_store(tmp_path)
        calls = []

        def mock_fetch(url, **kw):
            return {"gem": {"name": "org.test.gem.x", "version": "1.0.0"}, "$schemaVersion": "2.0.0"}

        with patch.object(store, "fetch_json_sync", side_effect=mock_fetch):
            store.refresh_sync(
                ["https://example.com/gem.json"],
                progress_callback=lambda msg, cur, tot: calls.append((msg, cur, tot)),
            )
        assert len(calls) >= 1


# ---------------------------------------------------------------------------
# TestExtractRemoteUrls
# ---------------------------------------------------------------------------

class TestExtractRemoteUrls:
    """Test URL extraction from JSON data."""

    def test_empty_data(self, tmp_path):
        store = _make_store(tmp_path)
        assert store._extract_remote_urls({}) == []

    def test_nested_remote_dict(self, tmp_path):
        store = _make_store(tmp_path)
        data = {"remote": {"gems": ["https://a.com/gem.json"], "engines": ["https://b.com/engine.json"]}}
        urls = store._extract_remote_urls(data)
        assert "https://a.com/gem.json" in urls
        assert "https://b.com/engine.json" in urls

    def test_top_level_arrays(self, tmp_path):
        store = _make_store(tmp_path)
        data = {"gems": ["https://a.com/gem.json"], "repos": ["https://b.com/repo.json"]}
        urls = store._extract_remote_urls(data)
        assert "https://a.com/gem.json" in urls
        assert "https://b.com/repo.json" in urls

    def test_mixed_sources(self, tmp_path):
        store = _make_store(tmp_path)
        data = {
            "remote": {"gems": ["https://a.com/1.json"]},
            "gems": ["https://a.com/2.json"],
        }
        urls = store._extract_remote_urls(data)
        assert len(urls) == 2


# ---------------------------------------------------------------------------
# TestSearchAndLookup
# ---------------------------------------------------------------------------

class TestSearchAndLookup:
    """Test search, get_by_name, get_versions, get_version."""

    def test_search_no_query_returns_all(self, tmp_path):
        store = _make_store(tmp_path)
        store.objects["gem:a"] = _make_remote_obj("a")
        store.objects["gem:b"] = _make_remote_obj("b")
        assert len(store.search()) == 2

    def test_search_filters_by_description(self, tmp_path):
        store = _make_store(tmp_path)
        store.objects["gem:a"] = _make_remote_obj("a", description="Physics engine")
        store.objects["gem:b"] = _make_remote_obj("b", description="Rendering")
        results = store.search("physics")
        assert len(results) == 1

    def test_get_by_name_hit(self, tmp_path):
        store = _make_store(tmp_path)
        obj = _make_remote_obj("org.o3de.gem.physx")
        store.objects["gem:org.o3de.gem.physx"] = obj
        assert store.get_by_name(ObjectType.GEM, "org.o3de.gem.physx") is obj

    def test_get_by_name_miss(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.get_by_name(ObjectType.GEM, "nope") is None

    def test_get_versions_sorted(self, tmp_path):
        store = _make_store(tmp_path)
        store.versions["gem:x"] = {
            "1.0.0": _make_remote_obj("x", "1.0.0"),
            "2.0.0": _make_remote_obj("x", "2.0.0"),
            "1.5.0": _make_remote_obj("x", "1.5.0"),
        }
        versions = store.get_versions(ObjectType.GEM, "x")
        assert versions == ["2.0.0", "1.5.0", "1.0.0"]

    def test_get_version_exact(self, tmp_path):
        store = _make_store(tmp_path)
        obj = _make_remote_obj("x", "1.0.0")
        store.versions["gem:x"] = {"1.0.0": obj}
        assert store.get_version(ObjectType.GEM, "x", "1.0.0") is obj

    def test_get_version_missing(self, tmp_path):
        store = _make_store(tmp_path)
        store.versions["gem:x"] = {"1.0.0": _make_remote_obj("x", "1.0.0")}
        assert store.get_version(ObjectType.GEM, "x", "9.9.9") is None

    def test_version_sort_key(self, tmp_path):
        store = _make_store(tmp_path)
        assert store._version_sort_key("2.0.0") > store._version_sort_key("1.9.9")
        assert store._version_sort_key("1.0.0") == store._version_sort_key("1.0.0")
        assert store._version_sort_key("1.10.0") > store._version_sort_key("1.9.0")


# ---------------------------------------------------------------------------
# TestDownloadSync
# ---------------------------------------------------------------------------

class TestDownloadSync:
    """Test synchronous download paths."""

    def test_git_clone_path(self, tmp_path):
        store = _make_store(tmp_path)
        obj = _make_remote_obj(
            "org.o3de.gem.clone",
            source_control_url="https://github.com/example/repo.git",
        )
        target = tmp_path / "dl"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            result = store.download_sync(obj, target)

        mock_run.assert_called_once()
        args = mock_run.call_args[0][0]
        assert "git" in args
        assert "clone" in args

    def test_git_clone_failure_raises(self, tmp_path):
        store = _make_store(tmp_path)
        obj = _make_remote_obj(
            "org.o3de.gem.bad",
            source_control_url="https://github.com/example/repo.git",
        )
        target = tmp_path / "dl"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="auth failed")
            with pytest.raises(StoreError, match="Git clone failed"):
                store.download_sync(obj, target)

    def test_zip_download_path(self, tmp_path):
        store = _make_store(tmp_path)
        obj = _make_remote_obj(
            "org.o3de.gem.zip",
            download_url="https://example.com/gem.zip",
        )
        target = tmp_path / "dl"

        # Create a minimal valid zip
        import zipfile, io
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("gem.json", '{"gem": {"name": "test"}}')
        zip_bytes = zip_buf.getvalue()

        mock_response = MagicMock()
        mock_response.headers = {"content-length": str(len(zip_bytes))}
        mock_response.iter_bytes.return_value = [zip_bytes]
        mock_response.raise_for_status = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        mock_client = MagicMock()
        mock_client.__enter__ = MagicMock(return_value=mock_client)
        mock_client.__exit__ = MagicMock(return_value=False)
        mock_client.stream.return_value = mock_response

        with patch("o3de_pilot.core.store.httpx.Client", return_value=mock_client), \
             patch("o3de_pilot.core.store.get_download_path", return_value=tmp_path / "downloads"):
            result = store.download_sync(obj, target)

        assert result.exists()

    def test_no_download_method_raises(self, tmp_path):
        store = _make_store(tmp_path)
        obj = _make_remote_obj("org.o3de.gem.nomethod")
        # No source_control_url and no download_url
        with pytest.raises(StoreError, match="No download method"):
            store.download_sync(obj, tmp_path / "dl")

    def test_integrity_check_on_clone(self, tmp_path):
        store = _make_store(tmp_path)
        obj = _make_remote_obj(
            "org.o3de.gem.integ",
            source_control_url="https://github.com/example/repo.git",
        )
        target = tmp_path / "dl"

        with patch("subprocess.run") as mock_run, \
             patch("o3de_pilot.core.store.verify_integrity") as mock_verify:
            mock_run.return_value = MagicMock(returncode=0, stderr="")
            store.download_sync(obj, target, expected_sha256="abc123")
            mock_verify.assert_called_once()


# ---------------------------------------------------------------------------
# TestRemoteObjectInheritance
# ---------------------------------------------------------------------------

class TestRemoteObjectInheritance:
    """Test effective source control URL inheritance."""

    def test_own_url_takes_precedence(self):
        obj = _make_remote_obj(
            source_control_url="https://own.com/repo",
            source_control_branch="main",
            inherited_source_control_url="https://parent.com/repo",
            inherited_source_control_branch="develop",
        )
        assert obj.effective_source_control_url == "https://own.com/repo"
        assert obj.effective_source_control_branch == "main"

    def test_inherits_from_parent(self):
        obj = _make_remote_obj(
            inherited_source_control_url="https://parent.com/repo",
            inherited_source_control_branch="develop",
        )
        assert obj.effective_source_control_url == "https://parent.com/repo"
        assert obj.effective_source_control_branch == "develop"

    def test_no_url_returns_none(self):
        obj = _make_remote_obj()
        assert obj.effective_source_control_url is None
        assert obj.effective_source_control_branch is None
