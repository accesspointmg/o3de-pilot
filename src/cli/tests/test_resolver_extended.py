# O3DE Pilot - Extended Resolver Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Extended tests for o3de_pilot.core.resolver — covers uncovered resolve paths."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from o3de_pilot.core.resolver import (
    Resolver,
    ResolverError,
    ResolvedObject,
    ObjectNameVersion,
    DependencyConflict,
    compute_file_hash,
)
from o3de_pilot.core.models import ObjectType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


def _make_manifest(tmp_path, *, engines=None, projects=None, gems=None,
                   templates=None, repos=None, overlays=None, remotes=None):
    """Create a minimal Schema 2.0.0 manifest and return its path."""
    manifest = {
        "$schemaVersion": "2.0.0",
        "o3de_manifest": {"name": "test"},
        "local": {
            "engines": engines or [],
            "projects": projects or [],
            "gems": gems or [],
            "templates": templates or [],
            "repos": repos or [],
            "overlays": overlays or [],
        },
        "remote": {"repos": remotes or []},
        "remotes": [],
    }
    mp = tmp_path / "o3de_manifest.json"
    _write_json(mp, manifest)
    return mp


def _make_gem(base: Path, name: str, version: str = "1.0.0", deps=None,
              optional_deps=None, peer_deps=None, children=None):
    """Create a gem directory with gem.json."""
    gem_dir = base / name
    gem_dir.mkdir(parents=True, exist_ok=True)
    gem_data = {
        "$schemaVersion": "2.0.0",
        "gem": {
            "name": name,
            "version": version,
            "display_name": name,
        },
    }
    if deps:
        gem_data["gem"]["dependent"] = {"gems": deps}
    if optional_deps:
        gem_data["gem"]["optional_dependent"] = {"gems": optional_deps}
    if peer_deps:
        gem_data["gem"]["peer_dependent"] = {"gems": peer_deps}
    if children:
        gem_data["children"] = children
    _write_json(gem_dir / "gem.json", gem_data)
    return gem_dir


def _make_engine(base: Path, name: str, version: str = "1.0.0", children=None):
    eng_dir = base / name
    eng_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        "engine": {"name": name, "version": version},
    }
    if children:
        data["children"] = children
    _write_json(eng_dir / "engine.json", data)
    return eng_dir


def _make_project(base: Path, name: str, version: str = "1.0.0", deps=None):
    proj_dir = base / name
    proj_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        "project": {"name": name, "version": version},
    }
    if deps:
        data["project"]["dependent"] = {"gems": deps}
    _write_json(proj_dir / "project.json", data)
    return proj_dir


def _make_template(base: Path, name: str, version: str = "1.0.0"):
    tpl_dir = base / name
    tpl_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        "template": {"name": name, "version": version},
    }
    _write_json(tpl_dir / "template.json", data)
    return tpl_dir


def _make_overlay(base: Path, name: str, version: str = "1.0.0"):
    ov_dir = base / name
    ov_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        "overlay": {"name": name, "version": version},
    }
    _write_json(ov_dir / "overlay.json", data)
    return ov_dir


# ---------------------------------------------------------------------------
# TestComputeFileHash
# ---------------------------------------------------------------------------

class TestComputeFileHash:
    def test_hash_of_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        h = compute_file_hash(f)
        assert isinstance(h, str) and len(h) == 64

    def test_nonexistent_returns_empty(self, tmp_path):
        assert compute_file_hash(tmp_path / "no_such_file.txt") == ""


# ---------------------------------------------------------------------------
# TestResolveWithRealFiles
# ---------------------------------------------------------------------------

class TestResolveWithRealFiles:
    """Test full resolve() using real temp files."""

    def test_resolve_single_gem(self, tmp_path):
        gem_dir = _make_gem(tmp_path, "org.test.gem.a")
        mp = _make_manifest(tmp_path, gems=[str(gem_dir)])

        r = Resolver(manifest_path=mp)
        with patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                    return_value=tmp_path / "resolved.json"):
            r.resolved_path = tmp_path / "resolved.json"
            objects = r.resolve()

        assert "org.test.gem.a" in objects
        assert objects["org.test.gem.a"].object_type == ObjectType.GEM

    def test_resolve_engine_with_children(self, tmp_path):
        # Engine with a child gem
        eng_dir = tmp_path / "engine"
        gem_child = _make_gem(eng_dir / "Gems", "org.child.gem")
        eng = _make_engine(tmp_path, "engine", children={
            "gems": ["Gems/org.child.gem/gem.json"],
        })
        mp = _make_manifest(tmp_path, engines=[str(eng)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        objects = r.resolve()

        assert "engine" in objects
        eng_obj = objects["engine"]
        child_names = [c.name for c in eng_obj.children]
        assert "org.child.gem" in child_names

    def test_resolve_project_with_deps(self, tmp_path):
        gem_dir = _make_gem(tmp_path, "org.test.gem.dep")
        proj_dir = _make_project(tmp_path, "myproject", deps=["org.test.gem.dep"])
        mp = _make_manifest(tmp_path, projects=[str(proj_dir)], gems=[str(gem_dir)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        objects = r.resolve()

        assert "myproject" in objects
        dep_names = [d.name for d in objects["myproject"].dependencies]
        assert "org.test.gem.dep" in dep_names

    def test_resolve_template(self, tmp_path):
        tpl = _make_template(tmp_path, "org.test.tpl")
        mp = _make_manifest(tmp_path, templates=[str(tpl)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        objects = r.resolve()

        assert "org.test.tpl" in objects
        assert objects["org.test.tpl"].object_type == ObjectType.TEMPLATE

    def test_resolve_overlay(self, tmp_path):
        ov = _make_overlay(tmp_path, "org.test.overlay")
        mp = _make_manifest(tmp_path, overlays=[str(ov)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        objects = r.resolve()

        assert "org.test.overlay" in objects

    def test_resolve_missing_manifest_raises(self, tmp_path):
        r = Resolver(manifest_path=tmp_path / "nonexistent.json")
        r.resolved_path = tmp_path / "resolved.json"
        with pytest.raises(ResolverError, match="Manifest not found"):
            r.resolve()

    def test_resolve_stale_paths_removed(self, tmp_path):
        # Include a path that doesn't exist
        mp = _make_manifest(tmp_path, gems=[str(tmp_path / "nonexistent_gem")])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()

        # Manifest should have been cleaned
        data = json.loads(mp.read_text())
        assert str(tmp_path / "nonexistent_gem") not in data.get("local", {}).get("gems", [])

    def test_resolve_url_in_repos_becomes_remote(self, tmp_path):
        mp = _make_manifest(tmp_path, repos=["https://example.com/repo.json"])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()

        assert "https://example.com/repo.json" in r.manifest_remotes

    def test_resolve_with_progress(self, tmp_path):
        gem_dir = _make_gem(tmp_path, "org.test.gem.prog")
        mp = _make_manifest(tmp_path, gems=[str(gem_dir)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"

        calls = []
        r.resolve(progress_callback=lambda msg, cur, tot: calls.append(msg))
        assert len(calls) >= 1
        assert any("Complete" in c for c in calls)


# ---------------------------------------------------------------------------
# TestDependencyDetection
# ---------------------------------------------------------------------------

class TestDependencyDetection:
    """Test dependency graph and conflict detection."""

    def test_no_conflicts_when_compatible(self, tmp_path):
        g1 = _make_gem(tmp_path, "org.a", deps=["org.shared>=1.0.0"])
        g2 = _make_gem(tmp_path, "org.b", deps=["org.shared>=1.0.0"])
        shared = _make_gem(tmp_path, "org.shared", "1.5.0")
        mp = _make_manifest(tmp_path, gems=[str(g1), str(g2), str(shared)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()
        assert len(r.conflicts) == 0

    def test_conflict_detected(self, tmp_path):
        g1 = _make_gem(tmp_path, "org.x", deps=["org.dep==1.0.0"])
        g2 = _make_gem(tmp_path, "org.y", deps=["org.dep==2.0.0"])
        dep = _make_gem(tmp_path, "org.dep", "1.0.0")
        mp = _make_manifest(tmp_path, gems=[str(g1), str(g2), str(dep)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()
        assert len(r.conflicts) >= 1

    def test_get_missing_dependencies(self, tmp_path):
        g = _make_gem(tmp_path, "org.needs", deps=["org.missing>=1.0.0"])
        mp = _make_manifest(tmp_path, gems=[str(g)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()

        missing = r.get_missing_dependencies()
        assert len(missing) == 1
        assert missing[0][1].name == "org.missing"

    def test_get_missing_optional_dependencies(self, tmp_path):
        g = _make_gem(tmp_path, "org.opt", optional_deps=["org.nice_to_have"])
        mp = _make_manifest(tmp_path, gems=[str(g)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()

        missing_opt = r.get_missing_optional_dependencies()
        assert len(missing_opt) == 1
        assert missing_opt[0][1].name == "org.nice_to_have"


# ---------------------------------------------------------------------------
# TestResolverSave
# ---------------------------------------------------------------------------

class TestResolverSave:
    """Test saving the resolved manifest."""

    def test_save_writes_json(self, tmp_path):
        gem_dir = _make_gem(tmp_path, "org.save.test")
        mp = _make_manifest(tmp_path, gems=[str(gem_dir)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()
        r.save()

        assert r.resolved_path.exists()
        saved = json.loads(r.resolved_path.read_text())
        assert isinstance(saved, dict)

    def test_dry_run_does_not_write(self, tmp_path):
        gem_dir = _make_gem(tmp_path, "org.dry.test")
        mp = _make_manifest(tmp_path, gems=[str(gem_dir)])

        r = Resolver(manifest_path=mp, dry_run=True)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()
        r.save()

        assert not r.resolved_path.exists()


# ---------------------------------------------------------------------------
# TestObjectNameVersionEdgeCases
# ---------------------------------------------------------------------------

class TestObjectNameVersionEdgeCases:
    def test_plain_name(self):
        onv = ObjectNameVersion("org.o3de.gem.atoms")
        assert onv.name == "org.o3de.gem.atoms"
        assert onv.matches("1.0.0")
        assert onv.matches("99.99.99")

    def test_exact_match(self):
        onv = ObjectNameVersion("org.o3de.gem.atoms==1.0.0")
        assert onv.matches("1.0.0")
        assert not onv.matches("2.0.0")

    def test_range(self):
        onv = ObjectNameVersion("org.o3de.gem.atoms>=1.0.0")
        assert onv.matches("1.0.0")
        assert onv.matches("2.0.0")
        assert not onv.matches("0.9.0")

    def test_invalid_version_accepted(self):
        onv = ObjectNameVersion("org.o3de.gem.atoms>=1.0.0")
        # Invalid versions are accepted as fallback
        assert onv.matches("not-a-version")


# ---------------------------------------------------------------------------
# TestResolverDedup
# ---------------------------------------------------------------------------

class TestResolverDedup:
    """Test that same object registered twice is deduplicated."""

    def test_same_gem_twice(self, tmp_path):
        gem_dir = _make_gem(tmp_path, "org.dup.gem")
        mp = _make_manifest(tmp_path, gems=[str(gem_dir), str(gem_dir)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()

        # Should only have one instance
        assert "org.dup.gem" in r.objects


# ---------------------------------------------------------------------------
# TestResolverLegacyFormat
# ---------------------------------------------------------------------------

class TestResolverLegacyFormat:
    """Test resolution of legacy (non-Schema-2.0.0) objects."""

    def test_legacy_gem_gets_upgraded(self, tmp_path):
        gem_dir = tmp_path / "legacy_gem"
        gem_dir.mkdir()
        _write_json(gem_dir / "gem.json", {
            "gem_name": "org.legacy.gem",
            "version": "1.0.0",
            "display_name": "Legacy Gem",
        })
        mp = _make_manifest(tmp_path, gems=[str(gem_dir)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()

        assert "org.legacy.gem" in r.objects


# ---------------------------------------------------------------------------
# TestResolverExternalSubdirectories
# ---------------------------------------------------------------------------

class TestResolverExternalSubdirectories:
    """Test external_subdirectories resolution (legacy format)."""

    def test_external_subdir_with_gem(self, tmp_path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        # Create a gem inside engine as external subdirectory
        ext_gem = _make_gem(engine_dir / "External", "org.ext.gem")
        _write_json(engine_dir / "engine.json", {
            "$schemaVersion": "2.0.0",
            "engine": {"name": "myengine", "version": "1.0.0"},
            "external_subdirectories": ["External/org.ext.gem"],
        })
        mp = _make_manifest(tmp_path, engines=[str(engine_dir)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()

        assert "org.ext.gem" in r.objects

    def test_external_subdir_nonexistent_skipped(self, tmp_path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        _write_json(engine_dir / "engine.json", {
            "$schemaVersion": "2.0.0",
            "engine": {"name": "eng2", "version": "1.0.0"},
            "external_subdirectories": ["DoesNotExist"],
        })
        mp = _make_manifest(tmp_path, engines=[str(engine_dir)])

        r = Resolver(manifest_path=mp)
        r.resolved_path = tmp_path / "resolved.json"
        r.resolve()

        assert "eng2" in r.objects  # Engine still resolves
