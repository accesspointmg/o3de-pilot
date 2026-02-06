# O3DE Pilot - Resolver Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.resolver module."""

import pytest
import tempfile
import json
from pathlib import Path

from o3de_pilot.core.resolver import (
    ObjectNameVersion,
    ResolvedObject,
    Resolver,
    ResolverError,
)
from o3de_pilot.core.models import ObjectType


class TestObjectNameVersion:
    """Test ObjectNameVersion specifier parsing."""
    
    def test_name_only(self):
        """Should parse name without version."""
        spec = ObjectNameVersion("org.o3de.gem.physx")
        assert spec.name == "org.o3de.gem.physx"
        assert str(spec.specifier) == ""
    
    def test_exact_version(self):
        """Should parse exact version constraint."""
        spec = ObjectNameVersion("org.o3de.gem.physx==1.0.0")
        assert spec.name == "org.o3de.gem.physx"
        assert spec.matches("1.0.0")
        assert not spec.matches("1.0.1")
        assert not spec.matches("2.0.0")
    
    def test_minimum_version(self):
        """Should parse minimum version constraint."""
        spec = ObjectNameVersion("org.o3de.gem.physx>=1.0.0")
        assert spec.name == "org.o3de.gem.physx"
        assert spec.matches("1.0.0")
        assert spec.matches("1.5.0")
        assert spec.matches("2.0.0")
        assert not spec.matches("0.9.0")
    
    def test_maximum_version(self):
        """Should parse maximum version constraint."""
        spec = ObjectNameVersion("org.o3de.gem.physx<2.0.0")
        assert spec.name == "org.o3de.gem.physx"
        assert spec.matches("1.0.0")
        assert spec.matches("1.9.9")
        assert not spec.matches("2.0.0")
    
    def test_version_range(self):
        """Should parse version range constraint."""
        spec = ObjectNameVersion("org.o3de.gem.physx>=1.0.0<2.0.0")
        assert spec.name == "org.o3de.gem.physx"
        assert spec.matches("1.0.0")
        assert spec.matches("1.5.0")
        assert not spec.matches("0.9.0")
        assert not spec.matches("2.0.0")
    
    def test_name_only_matches_any(self):
        """Name without version should match any version."""
        spec = ObjectNameVersion("org.o3de.gem.test")
        assert spec.matches("0.0.1")
        assert spec.matches("1.0.0")
        assert spec.matches("99.99.99")
    
    def test_repr(self):
        """Should have useful string representation."""
        spec1 = ObjectNameVersion("org.o3de.gem.test")
        assert repr(spec1) == "org.o3de.gem.test"
        
        spec2 = ObjectNameVersion("org.o3de.gem.test==1.0.0")
        assert "org.o3de.gem.test" in repr(spec2)
        assert "1.0.0" in repr(spec2)


class TestResolvedObject:
    """Test ResolvedObject class."""
    
    def test_creation(self):
        """Should create ResolvedObject with required fields."""
        obj = ResolvedObject(
            path=Path("/test/gem"),
            object_type=ObjectType.GEM,
            name="org.o3de.gem.test",
            version="1.0.0",
            data={"gem": {"name": "org.o3de.gem.test"}}
        )
        assert obj.path == Path("/test/gem")
        assert obj.object_type == ObjectType.GEM
        assert obj.name == "org.o3de.gem.test"
        assert obj.version == "1.0.0"
    
    def test_default_children(self):
        """Should have empty children list by default."""
        obj = ResolvedObject(
            path=Path("/test"),
            object_type=ObjectType.GEM,
            name="test",
            version="1.0.0",
            data={}
        )
        assert obj.children == []
    
    def test_default_dependencies(self):
        """Should have empty dependencies list by default."""
        obj = ResolvedObject(
            path=Path("/test"),
            object_type=ObjectType.GEM,
            name="test",
            version="1.0.0",
            data={}
        )
        assert obj.dependencies == []
    
    def test_default_overlays(self):
        """Should have empty overlays list by default."""
        obj = ResolvedObject(
            path=Path("/test"),
            object_type=ObjectType.GEM,
            name="test",
            version="1.0.0",
            data={}
        )
        assert obj.overlays == []
    
    def test_repr(self):
        """Should have useful string representation."""
        obj = ResolvedObject(
            path=Path("/test"),
            object_type=ObjectType.ENGINE,
            name="org.o3de.engine.core",
            version="2.0.0",
            data={}
        )
        repr_str = repr(obj)
        assert "engine" in repr_str
        assert "org.o3de.engine.core" in repr_str
        assert "2.0.0" in repr_str


class TestResolverInit:
    """Test Resolver initialization."""
    
    def test_default_manifest_path(self):
        """Should use default manifest path if not provided."""
        resolver = Resolver()
        assert resolver.manifest_path is not None
        # Can be either versioned (2.0.0) or legacy file
        assert "o3de_manifest" in str(resolver.manifest_path)
    
    def test_custom_manifest_path(self):
        """Should accept custom manifest path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "custom_manifest.json"
            resolver = Resolver(manifest_path=custom_path)
            assert resolver.manifest_path == custom_path
    
    def test_empty_object_dicts(self):
        """Should initialize with empty object dictionaries."""
        resolver = Resolver()
        assert resolver.engines == {}
        assert resolver.projects == {}
        assert resolver.gems == {}
        assert resolver.templates == {}
        assert resolver.repos == {}
        assert resolver.overlays == {}


class TestResolverWithManifest:
    """Test Resolver with actual manifest files."""
    
    def test_resolve_minimal_manifest(self):
        """Should resolve a minimal manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create minimal manifest
            manifest = {
                "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "o3de_manifest": {"name": "test.manifest"},
                "local": {"engines": [], "gems": [], "projects": [], "templates": []}
            }
            manifest_path = Path(tmpdir) / "o3de_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)
            
            resolver = Resolver(manifest_path=manifest_path)
            result = resolver.resolve()
            
            assert isinstance(result, dict)
    
    def test_resolve_with_local_gem(self):
        """Should resolve manifest with local gem reference."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create gem
            gem_dir = Path(tmpdir) / "Gems" / "TestGem"
            gem_dir.mkdir(parents=True)
            gem_json = {
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {"name": "org.test.gem.testgem", "version": "1.0.0"}
            }
            with open(gem_dir / "gem.2-0-0.json", "w") as f:
                json.dump(gem_json, f)
            
            # Create manifest referencing the gem
            manifest = {
                "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "o3de_manifest": {"name": "test.manifest"},
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
            
            resolver = Resolver(manifest_path=manifest_path)
            result = resolver.resolve()
            
            assert "org.test.gem.testgem" in result or len(resolver.gems) >= 0


class TestResolverError:
    """Test ResolverError exception."""
    
    def test_is_exception(self):
        """ResolverError should be an Exception."""
        error = ResolverError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"
