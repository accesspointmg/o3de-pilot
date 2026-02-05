# O3DE Pilot - Store Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.store module."""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta

from o3de_pilot.core.store import (
    Cache,
    RemoteObject,
    Store,
    StoreError,
    FetchError,
)
from o3de_pilot.core.models import ObjectType


class TestRemoteObject:
    """Test RemoteObject class."""
    
    def test_creation(self):
        """Should create RemoteObject with required fields."""
        obj = RemoteObject(
            url="https://example.com/gem.json",
            object_type=ObjectType.GEM,
            name="org.o3de.gem.atoms",
            version="1.0.0",
        )
        assert obj.name == "org.o3de.gem.atoms"
        assert obj.version == "1.0.0"
        assert obj.object_type == ObjectType.GEM
        assert obj.url == "https://example.com/gem.json"
    
    def test_optional_fields(self):
        """Should handle optional fields."""
        obj = RemoteObject(
            url="https://example.com/gem.json",
            object_type=ObjectType.GEM,
            name="org.o3de.gem.test",
            version="2.0.0",
            display_name="Test Gem",
            description="A test gem",
            download_url="https://example.com/gem.zip"
        )
        assert obj.display_name == "Test Gem"
        assert obj.description == "A test gem"
        assert obj.download_url == "https://example.com/gem.zip"
    
    def test_repr(self):
        """Should have useful string representation."""
        obj = RemoteObject(
            url="https://example.com",
            object_type=ObjectType.GEM,
            name="org.o3de.gem.test",
            version="1.0.0",
        )
        repr_str = repr(obj)
        assert "org.o3de.gem.test" in repr_str
        assert "1.0.0" in repr_str


class TestCache:
    """Test Cache class."""
    
    def test_init_creates_directory(self):
        """Should create cache directory on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "cache"
            assert not cache_dir.exists()
            
            cache = Cache(cache_dir)
            
            assert cache_dir.exists()
    
    def test_put_and_get(self):
        """Should store and retrieve JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            url = "https://example.com/gem.json"
            data = {"gem": {"name": "test", "version": "1.0.0"}}
            
            cache.put(url, data)
            result = cache.get(url)
            
            assert result == data
    
    def test_get_missing_returns_none(self):
        """Should return None for uncached URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            result = cache.get("https://nonexistent.com/file.json")
            
            assert result is None
    
    def test_put_with_etag(self):
        """Should store etag in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            url = "https://example.com/gem.json"
            data = {"test": "data"}
            etag = '"abc123"'
            
            cache.put(url, data, etag=etag)
            meta = cache.get_metadata(url)
            
            assert meta["etag"] == etag
    
    def test_metadata_contains_url_and_timestamp(self):
        """Should store URL and timestamp in metadata."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            url = "https://example.com/test.json"
            cache.put(url, {"data": True})
            meta = cache.get_metadata(url)
            
            assert meta["url"] == url
            assert "cached_at" in meta
    
    def test_is_stale_new_entry(self):
        """New entry should not be stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            url = "https://example.com/test.json"
            cache.put(url, {"data": True})
            
            assert cache.is_stale(url, max_age_hours=24) is False
    
    def test_is_stale_missing_entry(self):
        """Missing entry should be considered stale."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            assert cache.is_stale("https://nonexistent.com/file.json") is True
    
    def test_clear_single(self):
        """Should clear single URL from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            url1 = "https://example.com/a.json"
            url2 = "https://example.com/b.json"
            
            cache.put(url1, {"a": 1})
            cache.put(url2, {"b": 2})
            
            count = cache.clear(url1)
            
            assert count == 1
            assert cache.get(url1) is None
            assert cache.get(url2) == {"b": 2}
    
    def test_clear_all(self):
        """Should clear all entries from cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            cache.put("https://example.com/a.json", {"a": 1})
            cache.put("https://example.com/b.json", {"b": 2})
            cache.put("https://example.com/c.json", {"c": 3})
            
            count = cache.clear()
            
            assert count == 3
            assert cache.get("https://example.com/a.json") is None
            assert cache.get("https://example.com/b.json") is None
            assert cache.get("https://example.com/c.json") is None
    
    def test_url_hashing(self):
        """Different URLs should have different cache paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            path1 = cache._url_to_cache_path("https://example.com/a.json")
            path2 = cache._url_to_cache_path("https://example.com/b.json")
            
            assert path1 != path2
    
    def test_same_url_same_path(self):
        """Same URL should always map to same cache path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            
            url = "https://example.com/gem.json"
            path1 = cache._url_to_cache_path(url)
            path2 = cache._url_to_cache_path(url)
            
            assert path1 == path2


class TestStoreInit:
    """Test Store initialization."""
    
    def test_default_init(self):
        """Should initialize with defaults."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            store = Store(cache=cache)
            
            assert store.cache is not None
            assert store.objects == {}
    
    def test_custom_cache(self):
        """Should accept custom cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            store = Store(cache=cache, timeout=60.0)
            
            assert store.cache == cache
            assert store.timeout == 60.0


class TestStoreSearch:
    """Test Store search functionality."""
    
    def test_search_empty_store(self):
        """Should return empty list when no objects in store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            store = Store(cache=cache)
            
            results = store.search("test")
            
            assert results == []
    
    def test_search_by_name(self):
        """Should find objects by name."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            store = Store(cache=cache)
            
            # Add test objects directly
            store.objects["url1"] = RemoteObject(
                url="https://example.com/atoms.json",
                object_type=ObjectType.GEM,
                name="org.o3de.gem.atoms",
                version="1.0.0",
            )
            store.objects["url2"] = RemoteObject(
                url="https://example.com/other.json",
                object_type=ObjectType.GEM,
                name="org.o3de.gem.other",
                version="1.0.0",
            )
            
            results = store.search("atoms")
            
            assert len(results) == 1
            assert results[0].name == "org.o3de.gem.atoms"
    
    def test_search_by_type(self):
        """Should filter by object type."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            store = Store(cache=cache)
            
            store.objects["url1"] = RemoteObject(
                url="https://example.com/gem.json",
                object_type=ObjectType.GEM,
                name="org.o3de.gem.test",
                version="1.0.0",
            )
            store.objects["url2"] = RemoteObject(
                url="https://example.com/template.json",
                object_type=ObjectType.TEMPLATE,
                name="org.o3de.template.test",
                version="1.0.0",
            )
            
            gem_results = store.search("test", object_type=ObjectType.GEM)
            template_results = store.search("test", object_type=ObjectType.TEMPLATE)
            
            assert len(gem_results) == 1
            assert gem_results[0].object_type == ObjectType.GEM
            assert len(template_results) == 1
            assert template_results[0].object_type == ObjectType.TEMPLATE
    
    def test_search_case_insensitive(self):
        """Should search case-insensitively."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = Cache(Path(tmpdir))
            store = Store(cache=cache)
            
            store.objects["url1"] = RemoteObject(
                url="https://example.com/gem.json",
                object_type=ObjectType.GEM,
                name="org.o3de.gem.MyGem",
                version="1.0.0",
            )
            
            results = store.search("mygem")
            
            assert len(results) == 1


class TestExceptions:
    """Test exception classes."""
    
    def test_store_error(self):
        """StoreError should be an Exception."""
        error = StoreError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"
    
    def test_fetch_error(self):
        """FetchError should be a StoreError."""
        error = FetchError("fetch failed")
        assert isinstance(error, StoreError)
        assert str(error) == "fetch failed"
