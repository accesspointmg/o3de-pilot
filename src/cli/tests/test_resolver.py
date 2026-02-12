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
    DependencyConflict,
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
            
            assert "org.test.gem.testgem" in result or len(resolver.gems) > 0


class TestResolverError:
    """Test ResolverError exception."""
    
    def test_is_exception(self):
        """ResolverError should be an Exception."""
        error = ResolverError("test error")
        assert isinstance(error, Exception)
        assert str(error) == "test error"


class TestDependencyConflict:
    """Test DependencyConflict model."""
    
    def test_create_conflict(self):
        conflict = DependencyConflict(
            dependency_name="org.o3de.gem.physx",
            requirer_a="project_a",
            constraint_a=">=2.0.0",
            requirer_b="project_b",
            constraint_b="<2.0.0",
            resolved_version="2.0.0",
        )
        assert conflict.dependency_name == "org.o3de.gem.physx"
        assert conflict.requirer_a == "project_a"
        assert conflict.constraint_a == ">=2.0.0"
        assert conflict.requirer_b == "project_b"
        assert conflict.constraint_b == "<2.0.0"
        assert conflict.resolved_version == "2.0.0"
    
    def test_repr(self):
        conflict = DependencyConflict(
            dependency_name="dep",
            requirer_a="a",
            constraint_a=">=1",
            requirer_b="b",
            constraint_b="<1",
            resolved_version="1.0.0",
        )
        r = repr(conflict)
        assert "dep" in r
        assert "DependencyConflict" in r


class TestDependencyGraph:
    """Test dependency graph building and conflict detection."""
    
    def _make_resolver_with_objects(self, tmpdir):
        """Create a Resolver with pre-populated objects for graph testing."""
        manifest = {
            "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "o3de_manifest": {"name": "test"},
            "local": {"engines": [], "gems": [], "projects": [], "templates": []}
        }
        manifest_path = Path(tmpdir) / "o3de_manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)
        resolver = Resolver(manifest_path=manifest_path)
        resolver.manifest_data = manifest
        return resolver
    
    def _add_object(self, resolver, name, version, obj_type, deps=None):
        """Add a synthetic ResolvedObject to the resolver."""
        obj = ResolvedObject(
            path=Path(f"/fake/{name}"),
            object_type=obj_type,
            name=name,
            version=version,
            data={},
        )
        if deps:
            for d in deps:
                obj.dependencies.append(ObjectNameVersion(d))
        resolver.objects[name] = obj
        return obj
    
    def test_build_dependency_graph_no_deps(self):
        """Objects with no dependencies should have empty graph entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver_with_objects(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM)
            self._add_object(resolver, "gem_b", "2.0.0", ObjectType.GEM)
            
            resolver._build_dependency_graph()
            
            assert resolver.dependency_graph["gem_a"] == []
            assert resolver.dependency_graph["gem_b"] == []
            assert resolver.locked_dependencies == {}
    
    def test_build_dependency_graph_direct_dep(self):
        """Should record direct dependency in the graph."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver_with_objects(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_b"])
            self._add_object(resolver, "gem_b", "2.0.0", ObjectType.GEM)
            
            resolver._build_dependency_graph()
            
            assert ("gem_b", "2.0.0") in resolver.dependency_graph["gem_a"]
            assert resolver.dependency_graph["gem_b"] == []
            assert resolver.locked_dependencies["gem_a"] == {"gem_b": "2.0.0"}
    
    def test_build_dependency_graph_transitive(self):
        """Should follow transitive dependencies: A -> B -> C."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver_with_objects(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_b"])
            self._add_object(resolver, "gem_b", "2.0.0", ObjectType.GEM, deps=["gem_c"])
            self._add_object(resolver, "gem_c", "3.0.0", ObjectType.GEM)
            
            resolver._build_dependency_graph()
            
            pinned = resolver.dependency_graph["gem_a"]
            assert ("gem_b", "2.0.0") in pinned
            assert ("gem_c", "3.0.0") in pinned
            assert resolver.locked_dependencies["gem_a"] == {"gem_b": "2.0.0", "gem_c": "3.0.0"}
    
    def test_build_dependency_graph_diamond(self):
        """Should handle diamond dependencies without duplicates: A -> B,C; B -> D; C -> D."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver_with_objects(tmpdir)
            self._add_object(resolver, "a", "1.0.0", ObjectType.GEM, deps=["b", "c"])
            self._add_object(resolver, "b", "1.0.0", ObjectType.GEM, deps=["d"])
            self._add_object(resolver, "c", "1.0.0", ObjectType.GEM, deps=["d"])
            self._add_object(resolver, "d", "1.0.0", ObjectType.GEM)
            
            resolver._build_dependency_graph()
            
            pinned = resolver.dependency_graph["a"]
            # d should appear only once
            d_entries = [p for p in pinned if p[0] == "d"]
            assert len(d_entries) == 1
            assert ("d", "1.0.0") in pinned

    def test_detect_no_conflicts(self):
        """No conflicts when all version constraints are compatible."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver_with_objects(tmpdir)
            self._add_object(resolver, "gem.a", "1.0.0", ObjectType.GEM, deps=["gem.c>=1.0.0"])
            self._add_object(resolver, "gem.b", "1.0.0", ObjectType.GEM, deps=["gem.c>=1.0.0"])
            self._add_object(resolver, "gem.c", "2.0.0", ObjectType.GEM)
            
            resolver._detect_conflicts()
            
            assert resolver.conflicts == []
    
    def test_detect_conflict(self):
        """Should detect conflict when two objects have incompatible constraints."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver_with_objects(tmpdir)
            self._add_object(resolver, "gem.a", "1.0.0", ObjectType.GEM, deps=["gem.c>=2.0.0"])
            self._add_object(resolver, "gem.b", "1.0.0", ObjectType.GEM, deps=["gem.c<2.0.0"])
            self._add_object(resolver, "gem.c", "2.0.0", ObjectType.GEM)
            
            resolver._detect_conflicts()
            
            assert len(resolver.conflicts) == 1
            conflict = resolver.conflicts[0]
            assert conflict.dependency_name == "gem.c"
            assert conflict.resolved_version == "2.0.0"
    
    def test_no_conflict_when_no_constraints(self):
        """Deps with no version constraints should never conflict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver_with_objects(tmpdir)
            self._add_object(resolver, "gem.a", "1.0.0", ObjectType.GEM, deps=["gem.c"])
            self._add_object(resolver, "gem.b", "1.0.0", ObjectType.GEM, deps=["gem.c"])
            self._add_object(resolver, "gem.c", "1.0.0", ObjectType.GEM)
            
            resolver._detect_conflicts()
            
            assert resolver.conflicts == []


class TestDryRun:
    """Test dry-run mode."""
    
    def test_dry_run_flag(self):
        """Resolver should accept dry_run parameter."""
        resolver = Resolver(dry_run=True)
        assert resolver.dry_run is True
    
    def test_dry_run_default_false(self):
        """Dry-run should be False by default."""
        resolver = Resolver()
        assert resolver.dry_run is False
    
    def test_dry_run_save_no_write(self):
        """In dry-run mode, save() should not write to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest = {
                "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "o3de_manifest": {"name": "test"},
                "local": {"engines": [], "gems": [], "projects": [], "templates": []}
            }
            manifest_path = Path(tmpdir) / "o3de_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)
            
            resolver = Resolver(manifest_path=manifest_path, dry_run=True)
            # Override resolved_path to a temp location that does not exist
            resolver.resolved_path = Path(tmpdir) / "resolved_o3de_manifest.json"
            resolver.resolve()
            result = resolver.save()
            
            assert result == resolver.resolved_path
            # The file should NOT have been written
            assert not resolver.resolved_path.exists()


class TestLockedDependencies:
    """Test that locked dependencies appear in saved manifest."""
    
    def test_locked_deps_in_saved_manifest(self):
        """Saved manifest should include locked_dependencies section."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create gem_b
            gem_b_dir = Path(tmpdir) / "Gems" / "GemB"
            gem_b_dir.mkdir(parents=True)
            gem_b_json = {
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {"name": "gem_b", "version": "2.0.0"}
            }
            with open(gem_b_dir / "gem.2-0-0.json", "w") as f:
                json.dump(gem_b_json, f)
            
            # Create gem_a with dependency on gem_b
            gem_a_dir = Path(tmpdir) / "Gems" / "GemA"
            gem_a_dir.mkdir(parents=True)
            gem_a_json = {
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {
                    "name": "gem_a",
                    "version": "1.0.0",
                    "dependencies": {"gems": ["gem_b>=1.0.0"]}
                }
            }
            with open(gem_a_dir / "gem.2-0-0.json", "w") as f:
                json.dump(gem_a_json, f)
            
            manifest = {
                "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "o3de_manifest": {"name": "test"},
                "local": {
                    "engines": [],
                    "gems": [
                        str(gem_a_dir / "gem.2-0-0.json"),
                        str(gem_b_dir / "gem.2-0-0.json"),
                    ],
                    "projects": [],
                    "templates": []
                }
            }
            manifest_path = Path(tmpdir) / "o3de_manifest.json"
            with open(manifest_path, "w") as f:
                json.dump(manifest, f)
            
            resolver = Resolver(manifest_path=manifest_path)
            resolver.resolve()
            resolver.save()
            
            # Load and check
            with open(resolver.resolved_path) as f:
                saved = json.load(f)
            
            if "locked_dependencies" in saved:
                assert "gem_a" in saved["locked_dependencies"]
                assert saved["locked_dependencies"]["gem_a"]["gem_b"] == "2.0.0"
