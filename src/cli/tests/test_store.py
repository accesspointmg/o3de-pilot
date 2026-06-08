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
    IntegrityError,
    compute_sha256,
    verify_integrity,
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


class TestIntegrity:
    """Test SHA-256 integrity verification."""
    
    def test_compute_sha256_file(self):
        """Should compute SHA-256 hash of a file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("hello world")
            
            h = compute_sha256(test_file)
            assert isinstance(h, str)
            assert len(h) == 64  # SHA-256 hex digest is 64 chars
    
    def test_compute_sha256_deterministic(self):
        """Same content should produce same hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "a.txt"
            f2 = Path(tmpdir) / "b.txt"
            f1.write_text("same content")
            f2.write_text("same content")
            
            assert compute_sha256(f1) == compute_sha256(f2)
    
    def test_compute_sha256_different(self):
        """Different content should produce different hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "a.txt"
            f2 = Path(tmpdir) / "b.txt"
            f1.write_text("content a")
            f2.write_text("content b")
            
            assert compute_sha256(f1) != compute_sha256(f2)
    
    def test_compute_sha256_directory(self):
        """Should compute hash for a directory by hashing all files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            d = Path(tmpdir) / "mydir"
            d.mkdir()
            (d / "a.txt").write_text("file a")
            (d / "b.txt").write_text("file b")
            
            h = compute_sha256(d)
            assert isinstance(h, str)
            assert len(h) == 64
    
    def test_verify_integrity_pass(self):
        """Should return True when hash matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test data")
            
            expected = compute_sha256(test_file)
            assert verify_integrity(test_file, expected) is True
    
    def test_verify_integrity_fail(self):
        """Should raise IntegrityError when hash mismatches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("test data")
            
            with pytest.raises(IntegrityError, match="Integrity check failed"):
                verify_integrity(test_file, "0000000000000000000000000000000000000000000000000000000000000000")
    
    def test_integrity_error_is_store_error(self):
        """IntegrityError should be a StoreError."""
        error = IntegrityError("bad hash")
        assert isinstance(error, StoreError)


class TestDeprecationWarnings:
    """Test deprecation warning emit during resolution."""
    
    def test_deprecated_object_logs_warning(self, caplog):
        """When an object has deprecated field, resolver should log warning."""
        import logging
        
        with tempfile.TemporaryDirectory() as tmpdir:
            gem_dir = Path(tmpdir) / "Gems" / "OldGem"
            gem_dir.mkdir(parents=True)
            gem_json = {
                "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {
                    "name": "org.test.gem.oldgem",
                    "version": "1.0.0",
                    "deprecated": {
                        "message": "Use newgem instead",
                        "replacement": "org.test.gem.newgem"
                    }
                }
            }
            with open(gem_dir / "gem.2-0-0.json", "w") as f:
                json.dump(gem_json, f)
            
            manifest = {
                "$schema": "https://canonical.o3de.org/o3de-manifest-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "o3de_manifest": {"name": "test"},
                "local": {
                    "engines": [],
                    "gems": [str(gem_dir / "gem.2-0-0.json")],
                    "projects": [],
                    "templates": []
                }
            }
            manifest_path = Path(tmpdir) / "o3de_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)
            
            from o3de_pilot.core.resolver import Resolver
            
            resolver = Resolver(manifest_path=manifest_path)
            
            with caplog.at_level(logging.WARNING, logger="o3de_pilot.resolver"):
                resolver.resolve()
            
            assert "org.test.gem.oldgem" in resolver.objects
            assert any("DEPRECATED" in r.message and "oldgem" in r.message for r in caplog.records)


class TestMissingDependencies:
    """Test get_missing_dependencies."""

    def test_no_missing_deps(self):
        """When all deps are present, should return empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two gems, one depending on the other
            gem_a_dir = Path(tmpdir) / "Gems" / "GemA"
            gem_a_dir.mkdir(parents=True)
            with open(gem_a_dir / "gem.2-0-0.json", "w") as f:
                json.dump({
                    "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
                    "$schemaVersion": "2.0.0",
                    "gem": {"name": "gem.a", "version": "1.0.0", "dependent": {"gems": ["gem.b"]}}
                }, f)
            
            gem_b_dir = Path(tmpdir) / "Gems" / "GemB"
            gem_b_dir.mkdir(parents=True)
            with open(gem_b_dir / "gem.2-0-0.json", "w") as f:
                json.dump({
                    "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
                    "$schemaVersion": "2.0.0",
                    "gem": {"name": "gem.b", "version": "1.0.0"}
                }, f)
            
            manifest = {
                "$schema": "https://canonical.o3de.org/o3de-manifest-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "o3de_manifest": {"name": "test"},
                "local": {
                    "engines": [],
                    "gems": [str(gem_a_dir / "gem.2-0-0.json"), str(gem_b_dir / "gem.2-0-0.json")],
                    "projects": [],
                    "templates": []
                }
            }
            manifest_path = Path(tmpdir) / "o3de_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)
            
            from o3de_pilot.core.resolver import Resolver
            resolver = Resolver(manifest_path=manifest_path)
            resolver.resolve()
            
            missing = resolver.get_missing_dependencies()
            assert missing == []
    
    def test_missing_dep_detected(self):
        """When a dep is missing, should be reported."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gem_a_dir = Path(tmpdir) / "Gems" / "GemA"
            gem_a_dir.mkdir(parents=True)
            with open(gem_a_dir / "gem.2-0-0.json", "w") as f:
                json.dump({
                    "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
                    "$schemaVersion": "2.0.0",
                    "gem": {"name": "gem.a", "version": "1.0.0", "dependent": {"gems": ["gem.missing"]}}
                }, f)
            
            manifest = {
                "$schema": "https://canonical.o3de.org/o3de-manifest-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "o3de_manifest": {"name": "test"},
                "local": {
                    "engines": [],
                    "gems": [str(gem_a_dir / "gem.2-0-0.json")],
                    "projects": [],
                    "templates": []
                }
            }
            manifest_path = Path(tmpdir) / "o3de_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)
            
            from o3de_pilot.core.resolver import Resolver
            resolver = Resolver(manifest_path=manifest_path)
            resolver.resolve()
            
            missing = resolver.get_missing_dependencies()
            assert len(missing) == 1
            assert missing[0][0] == "gem.a"
            assert missing[0][1].name == "gem.missing"


class TestSHA256Wiring:
    """Test that SHA-256 is extracted from metadata and wired to downloads."""

    def test_remote_object_stores_sha256(self):
        """RemoteObject should accept and store source_sha256."""
        obj = RemoteObject(
            url="https://example.com/gem.json",
            object_type=ObjectType.GEM,
            name="test.gem",
            version="1.0.0",
            source_sha256="abcd1234" * 8,
        )
        assert obj.source_sha256 == "abcd1234" * 8

    def test_remote_object_sha256_defaults_none(self):
        """RemoteObject without sha256 should default to None."""
        obj = RemoteObject(
            url="https://example.com/gem.json",
            object_type=ObjectType.GEM,
            name="test.gem",
            version="1.0.0",
        )
        assert obj.source_sha256 is None

    def test_parse_extracts_source_sha256(self):
        """_parse_remote_object should extract source_sha256 from download block."""
        store = Store.__new__(Store)
        data = {
            "gem_name": "test.gem",
            "version": "1.0.0",
            "download": {
                "source": "https://example.com/test.zip",
                "source_sha256": "a" * 64,
            },
        }
        obj = store._parse_remote_object(
            url="https://example.com/test.json",
            data=data,
            obj_type=ObjectType.GEM,
        )
        assert obj is not None
        assert obj.source_sha256 == "a" * 64
        assert obj.download_url == "https://example.com/test.zip"

    def test_parse_no_download_block_sha256_none(self):
        """Without download block, source_sha256 should be None."""
        store = Store.__new__(Store)
        data = {
            "gem_name": "test.gem",
            "version": "1.0.0",
        }
        obj = store._parse_remote_object(
            url="https://example.com/test.json",
            data=data,
            obj_type=ObjectType.GEM,
        )
        assert obj is not None
        assert obj.source_sha256 is None

    def test_parse_download_without_sha256(self):
        """Download block without source_sha256 should leave it None."""
        store = Store.__new__(Store)
        data = {
            "gem_name": "test.gem",
            "version": "1.0.0",
            "download": {
                "source": "https://example.com/test.zip",
            },
        }
        obj = store._parse_remote_object(
            url="https://example.com/test.json",
            data=data,
            obj_type=ObjectType.GEM,
        )
        assert obj is not None
        assert obj.source_sha256 is None


# ── Remote dependency parsing (J6) ──────────────────────────────────────────


class TestRemoteDependencyParsing:
    """Test that _parse_remote_object extracts dependency specifiers."""

    def test_schema_2_nested_dependent(self):
        """Schema 2.0 nested dependent field should be parsed."""
        store = Store.__new__(Store)
        data = {
            "gem": {
                "gem_name": "org.o3de.gem.test",
                "version": "1.0.0",
                "dependent": {
                    "gems": ["org.o3de.gem.core>=1.0.0", "org.o3de.gem.atom"],
                    "engines": ["org.o3de.engine.main>=2.0.0"],
                },
            },
        }
        obj = store._parse_remote_object(
            url="https://example.com/test.json",
            data=data,
            obj_type=ObjectType.GEM,
        )
        assert obj is not None
        assert len(obj.dependencies) == 3
        assert "org.o3de.gem.core>=1.0.0" in obj.dependencies
        assert "org.o3de.gem.atom" in obj.dependencies
        assert "org.o3de.engine.main>=2.0.0" in obj.dependencies

    def test_root_level_dependent(self):
        """Root-level dependent field should be parsed as fallback."""
        store = Store.__new__(Store)
        data = {
            "gem_name": "test.gem",
            "version": "1.0.0",
            "dependent": {
                "gems": ["dep_a", "dep_b>=2.0.0"],
            },
        }
        obj = store._parse_remote_object(
            url="https://example.com/test.json",
            data=data,
            obj_type=ObjectType.GEM,
        )
        assert obj is not None
        assert len(obj.dependencies) == 2
        assert "dep_a" in obj.dependencies
        assert "dep_b>=2.0.0" in obj.dependencies

    def test_no_dependent_field(self):
        """Missing dependent field should yield empty deps list."""
        store = Store.__new__(Store)
        data = {
            "gem_name": "test.gem",
            "version": "1.0.0",
        }
        obj = store._parse_remote_object(
            url="https://example.com/test.json",
            data=data,
            obj_type=ObjectType.GEM,
        )
        assert obj is not None
        assert obj.dependencies == []

    def test_dependent_non_string_skipped(self):
        """Non-string entries in dependency lists should be skipped."""
        store = Store.__new__(Store)
        data = {
            "gem_name": "test.gem",
            "version": "1.0.0",
            "dependent": {
                "gems": ["valid_dep", 42, None, "another_dep"],
            },
        }
        obj = store._parse_remote_object(
            url="https://example.com/test.json",
            data=data,
            obj_type=ObjectType.GEM,
        )
        assert obj is not None
        assert obj.dependencies == ["valid_dep", "another_dep"]
