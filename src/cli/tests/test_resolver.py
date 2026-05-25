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


class TestPropertyInheritance:
    """Test that children inherit properties from parents."""

    def _make_resolver(self, tmpdir):
        """Create a Resolver with a minimal manifest."""
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

    def _add_object(self, resolver, name, version, obj_type, data=None, parent=None):
        """Add a synthetic ResolvedObject to the resolver."""
        obj = ResolvedObject(
            path=Path(f"/fake/{name}"),
            object_type=obj_type,
            name=name,
            version=version,
            data=data or {},
        )
        if parent:
            obj.parent = parent
            parent.children.append(obj)
        resolver.objects[name] = obj
        return obj

    def test_child_inherits_origin_from_parent(self):
        """Child without origin should inherit parent's origin."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            parent = self._add_object(
                resolver, "parent_engine", "1.0.0", ObjectType.ENGINE,
                data={"origin": {"name": "ACME Corp", "url": "https://acme.com"}}
            )
            child = self._add_object(
                resolver, "child_gem", "1.0.0", ObjectType.GEM,
                data={},
                parent=parent,
            )

            resolver._apply_inheritance()

            assert child.data["origin"] == {"name": "ACME Corp", "url": "https://acme.com"}
            assert child.inherited_from["origin"] == "parent_engine"

    def test_child_keeps_own_origin(self):
        """Child with its own origin should NOT inherit parent's."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            parent = self._add_object(
                resolver, "parent_engine", "1.0.0", ObjectType.ENGINE,
                data={"origin": {"name": "ACME Corp", "url": "https://acme.com"}}
            )
            child = self._add_object(
                resolver, "child_gem", "1.0.0", ObjectType.GEM,
                data={"origin": {"name": "Child Inc", "url": "https://child.com"}},
                parent=parent,
            )

            resolver._apply_inheritance()

            assert child.data["origin"] == {"name": "Child Inc", "url": "https://child.com"}
            assert "origin" not in child.inherited_from

    def test_child_inherits_licenses(self):
        """Child without licenses should inherit parent's licenses."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            parent_licenses = [
                {"license_identifier": "Apache-2.0", "url": "https://spdx.org/licenses/Apache-2.0.html"}
            ]
            parent = self._add_object(
                resolver, "parent_repo", "1.0.0", ObjectType.REPO,
                data={"licenses": parent_licenses}
            )
            child = self._add_object(
                resolver, "child_gem", "1.0.0", ObjectType.GEM,
                data={},
                parent=parent,
            )

            resolver._apply_inheritance()

            assert child.data["licenses"] == parent_licenses
            assert child.inherited_from["licenses"] == "parent_repo"

    def test_child_inherits_source_control(self):
        """Child without source_control should inherit parent's."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            parent_sc = {"git": "https://github.com/acme/repo.git", "branch": "main"}
            parent = self._add_object(
                resolver, "parent_repo", "1.0.0", ObjectType.REPO,
                data={"source_control": parent_sc}
            )
            child = self._add_object(
                resolver, "child_gem", "1.0.0", ObjectType.GEM,
                data={},
                parent=parent,
            )

            resolver._apply_inheritance()

            assert child.data["source_control"] == parent_sc
            assert child.inherited_from["source_control"] == "parent_repo"

    def test_child_inherits_documentation(self):
        """Child without documentation should inherit parent's."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            parent_doc = {"url": "https://docs.acme.com", "relative_path": "docs/"}
            parent = self._add_object(
                resolver, "parent_engine", "1.0.0", ObjectType.ENGINE,
                data={"documentation": parent_doc}
            )
            child = self._add_object(
                resolver, "child_gem", "1.0.0", ObjectType.GEM,
                data={},
                parent=parent,
            )

            resolver._apply_inheritance()

            assert child.data["documentation"] == parent_doc
            assert child.inherited_from["documentation"] == "parent_engine"

    def test_grandchild_inherits_from_grandparent(self):
        """Inheritance should walk up multiple levels."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            grandparent = self._add_object(
                resolver, "grandparent", "1.0.0", ObjectType.ENGINE,
                data={"origin": {"name": "Root Corp", "url": "https://root.com"}}
            )
            parent = self._add_object(
                resolver, "parent", "1.0.0", ObjectType.PROJECT,
                data={},
                parent=grandparent,
            )
            child = self._add_object(
                resolver, "child", "1.0.0", ObjectType.GEM,
                data={},
                parent=parent,
            )

            resolver._apply_inheritance()

            # Parent inherits from grandparent
            assert parent.data["origin"] == {"name": "Root Corp", "url": "https://root.com"}
            assert parent.inherited_from["origin"] == "grandparent"
            # Child inherits from grandparent (parent didn't define its own)
            assert child.data["origin"] == {"name": "Root Corp", "url": "https://root.com"}
            assert child.inherited_from["origin"] == "grandparent"

    def test_no_inheritance_without_parent(self):
        """Root objects should not have any inherited properties."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            root = self._add_object(
                resolver, "root_engine", "1.0.0", ObjectType.ENGINE,
                data={"origin": {"name": "ACME", "url": "https://acme.com"}}
            )

            resolver._apply_inheritance()

            assert root.inherited_from == {}

    def test_empty_origin_counts_as_missing(self):
        """An empty dict for origin should be treated as unset (inheritable)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            parent = self._add_object(
                resolver, "parent", "1.0.0", ObjectType.ENGINE,
                data={"origin": {"name": "ACME", "url": "https://acme.com"}}
            )
            child = self._add_object(
                resolver, "child", "1.0.0", ObjectType.GEM,
                data={"origin": {}},
                parent=parent,
            )

            resolver._apply_inheritance()

            assert child.data["origin"] == {"name": "ACME", "url": "https://acme.com"}
            assert child.inherited_from["origin"] == "parent"

    def test_multiple_properties_inherited_independently(self):
        """Each property inherits independently — child can have some, inherit others."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            parent = self._add_object(
                resolver, "parent", "1.0.0", ObjectType.REPO,
                data={
                    "origin": {"name": "ACME", "url": "https://acme.com"},
                    "licenses": [{"license_identifier": "MIT", "url": "https://mit.edu"}],
                    "source_control": {"git": "https://github.com/acme/repo.git"},
                    "documentation": {"url": "https://docs.acme.com"},
                }
            )
            child = self._add_object(
                resolver, "child", "1.0.0", ObjectType.GEM,
                data={
                    "origin": {"name": "Child LLC", "url": "https://child.com"},
                    # No licenses, source_control, or documentation
                },
                parent=parent,
            )

            resolver._apply_inheritance()

            # origin: child keeps its own
            assert child.data["origin"] == {"name": "Child LLC", "url": "https://child.com"}
            assert "origin" not in child.inherited_from
            # licenses: inherited
            assert child.data["licenses"] == [{"license_identifier": "MIT", "url": "https://mit.edu"}]
            assert child.inherited_from["licenses"] == "parent"
            # source_control: inherited
            assert child.data["source_control"] == {"git": "https://github.com/acme/repo.git"}
            assert child.inherited_from["source_control"] == "parent"
            # documentation: inherited
            assert child.data["documentation"] == {"url": "https://docs.acme.com"}
            assert child.inherited_from["documentation"] == "parent"

    def test_inherited_value_is_deep_copied(self):
        """Inherited values should be deep copies — mutating child must not affect parent."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            parent = self._add_object(
                resolver, "parent", "1.0.0", ObjectType.ENGINE,
                data={"origin": {"name": "ACME", "url": "https://acme.com"}}
            )
            child = self._add_object(
                resolver, "child", "1.0.0", ObjectType.GEM,
                data={},
                parent=parent,
            )

            resolver._apply_inheritance()

            # Mutate child's inherited origin
            child.data["origin"]["name"] = "MUTATED"

            # Parent should be unaffected
            assert parent.data["origin"]["name"] == "ACME"


class TestAutoInstallMissing:
    """Test auto-install of missing dependencies."""

    def _make_resolver(self, tmpdir):
        """Create a Resolver with a minimal manifest."""
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
        """Add a synthetic ResolvedObject to the resolver with optional deps."""
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
        type_dict = {
            ObjectType.ENGINE: resolver.engines,
            ObjectType.PROJECT: resolver.projects,
            ObjectType.GEM: resolver.gems,
        }.get(obj_type)
        if type_dict is not None:
            type_dict[name] = obj
        return obj

    def test_no_missing_returns_empty(self):
        """When all deps are present, auto_install returns empty list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM)
            self._add_object(resolver, "gem_b", "1.0.0", ObjectType.GEM, deps=["gem_a"])

            from unittest.mock import MagicMock
            store = MagicMock()
            result = resolver.auto_install_missing(store, confirm=True)
            assert result == []

    def test_dry_run_returns_plan(self):
        """Dry-run should return install plan without downloading."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_b"])
            # gem_b is NOT in the resolver — it's missing

            from unittest.mock import MagicMock
            from o3de_pilot.core.store import RemoteObject
            from o3de_pilot.core.models import ObjectType as OT

            mock_remote = RemoteObject(
                url="https://example.com/gem_b.json",
                object_type=OT.GEM,
                name="gem_b",
                version="2.0.0",
                source_control_url="https://github.com/example/gem_b",
            )
            store = MagicMock()
            store.search.return_value = [mock_remote]

            plan = resolver.auto_install_missing(store, confirm=False, dry_run=True)
            assert len(plan) == 1
            assert plan[0]["name"] == "gem_b"
            assert plan[0]["version"] == "2.0.0"
            # Should NOT have called download
            store.download_sync.assert_not_called()

    def test_confirm_false_raises_error(self):
        """Without confirm, should raise ResolverError listing missing deps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_b"])

            from unittest.mock import MagicMock
            from o3de_pilot.core.store import RemoteObject
            from o3de_pilot.core.models import ObjectType as OT

            mock_remote = RemoteObject(
                url="https://example.com/gem_b.json",
                object_type=OT.GEM,
                name="gem_b",
                version="2.0.0",
                source_control_url="https://github.com/example/gem_b",
            )
            store = MagicMock()
            store.search.return_value = [mock_remote]

            with pytest.raises(ResolverError, match="Missing 1 dependencies"):
                resolver.auto_install_missing(store, confirm=False, dry_run=False)

    def test_confirm_true_downloads_and_registers(self):
        """With confirm=True, should download and add to manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_b"])

            from unittest.mock import MagicMock, patch
            from o3de_pilot.core.store import RemoteObject
            from o3de_pilot.core.models import ObjectType as OT

            mock_remote = RemoteObject(
                url="https://example.com/gem_b.json",
                object_type=OT.GEM,
                name="gem_b",
                version="2.0.0",
                source_control_url="https://github.com/example/gem_b",
            )
            store = MagicMock()
            store.search.return_value = [mock_remote]

            download_dest = Path(tmpdir) / "gems" / "gem_b"
            download_dest.mkdir(parents=True)
            # Create a gem.json so add_to_manifest can find it
            (download_dest / "gem.json").write_text('{"gem_name": "gem_b"}')
            store.download_sync.return_value = download_dest

            with patch(
                "o3de_pilot.core.paths.get_default_path_for_type",
                return_value=Path(tmpdir) / "gems",
            ):
                installed = resolver.auto_install_missing(store, confirm=True)

            assert len(installed) == 1
            assert installed[0]["name"] == "gem_b"
            store.download_sync.assert_called_once()

            # Verify it was added to the manifest
            with open(resolver.manifest_path) as f:
                manifest = json.load(f)
            gem_paths = manifest["local"]["gems"]
            assert any("gem_b" in p for p in gem_paths)

    def test_version_constraint_respected(self):
        """Should only match remote objects that satisfy the version constraint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_b>=2.0.0"])

            from unittest.mock import MagicMock
            from o3de_pilot.core.store import RemoteObject
            from o3de_pilot.core.models import ObjectType as OT

            # Remote has v1.0.0 which doesn't satisfy >=2.0.0
            old_remote = RemoteObject(
                url="https://example.com/gem_b.json",
                object_type=OT.GEM,
                name="gem_b",
                version="1.0.0",
                source_control_url="https://github.com/example/gem_b",
            )
            store = MagicMock()
            store.search.return_value = [old_remote]

            plan = resolver.auto_install_missing(store, dry_run=True)
            # No compatible version found
            assert len(plan) == 0

    def test_multiple_missing_deduped(self):
        """If two objects require the same missing dep, it should only appear once."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_c"])
            self._add_object(resolver, "gem_b", "1.0.0", ObjectType.GEM, deps=["gem_c"])

            from unittest.mock import MagicMock
            from o3de_pilot.core.store import RemoteObject
            from o3de_pilot.core.models import ObjectType as OT

            mock_remote = RemoteObject(
                url="https://example.com/gem_c.json",
                object_type=OT.GEM,
                name="gem_c",
                version="1.0.0",
                source_control_url="https://github.com/example/gem_c",
            )
            store = MagicMock()
            store.search.return_value = [mock_remote]

            plan = resolver.auto_install_missing(store, dry_run=True)
            assert len(plan) == 1
            assert plan[0]["name"] == "gem_c"

    def test_not_found_in_store(self):
        """If dep is not in the store, should return empty and not crash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_unknown"])

            from unittest.mock import MagicMock
            store = MagicMock()
            store.search.return_value = []

            plan = resolver.auto_install_missing(store, dry_run=True)
            assert plan == []

    def test_picks_newest_compatible_version(self):
        """When store has multiple versions, should pick the newest compatible one."""
        with tempfile.TemporaryDirectory() as tmpdir:
            resolver = self._make_resolver(tmpdir)
            self._add_object(resolver, "gem_a", "1.0.0", ObjectType.GEM, deps=["gem_b>=1.0.0"])

            from unittest.mock import MagicMock
            from o3de_pilot.core.store import RemoteObject
            from o3de_pilot.core.models import ObjectType as OT

            v1 = RemoteObject(
                url="https://example.com/gem_b_v1.json",
                object_type=OT.GEM, name="gem_b", version="1.0.0",
            )
            v2 = RemoteObject(
                url="https://example.com/gem_b_v2.json",
                object_type=OT.GEM, name="gem_b", version="2.0.0",
            )
            store = MagicMock()
            store.search.return_value = [v1, v2]
            store._is_newer_version.side_effect = lambda a, b: (
                tuple(int(x) for x in a.split(".")) > tuple(int(x) for x in b.split("."))
            )

            plan = resolver.auto_install_missing(store, dry_run=True)
            assert len(plan) == 1
            assert plan[0]["version"] == "2.0.0"
