# O3DE Pilot - Solver Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.solver module."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from o3de_pilot.core.solver import (
    CandidateStatus,
    Candidate,
    Requirement,
    OverlayEntry,
    SolveResult,
    O3DEProvider,
    O3DEReporter,
    solve_for_workspace,
)
from o3de_pilot.core.resolver import ObjectNameVersion, ResolvedObject, Resolver
from o3de_pilot.core.models import ObjectType


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_resolved(
    name: str,
    version: str = "1.0.0",
    object_type: ObjectType = ObjectType.GEM,
    deps: list[str] | None = None,
    children: list[ResolvedObject] | None = None,
    data: dict | None = None,
) -> ResolvedObject:
    """Create a minimal ResolvedObject for testing."""
    obj = ResolvedObject(
        path=Path(f"/test/{name}"),
        object_type=object_type,
        name=name,
        version=version,
        data=data or {},
    )
    if deps:
        obj.dependencies = [ObjectNameVersion(d) for d in deps]
    if children:
        obj.children = children
    return obj


def _make_resolver(*objects: ResolvedObject) -> MagicMock:
    """Create a mock Resolver with the given objects."""
    resolver = MagicMock(spec=Resolver)
    resolver.objects = {obj.name: obj for obj in objects}
    resolver.overlays = {}
    return resolver


# ── Requirement tests ────────────────────────────────────────────────────────


class TestRequirement:
    """Test Requirement dataclass."""

    def test_from_specifier_name_only(self):
        """Should parse a bare name."""
        req = Requirement.from_specifier("org.o3de.gem.physx")
        assert req.name == "org.o3de.gem.physx"
        assert str(req.specifier) == ""

    def test_from_specifier_with_version(self):
        """Should parse name with version constraint."""
        req = Requirement.from_specifier("org.o3de.gem.atom>=1.0.0")
        assert req.name == "org.o3de.gem.atom"
        assert "1.0.0" in str(req.specifier)

    def test_repr(self):
        """Should have useful repr."""
        req = Requirement.from_specifier("org.o3de.gem.atom>=1.0.0")
        assert "org.o3de.gem.atom" in repr(req)

    def test_hash_equals(self):
        """Requirements with same name should be equal and hash equal."""
        r1 = Requirement(name="test")
        r2 = Requirement(name="test")
        assert r1 == r2
        assert hash(r1) == hash(r2)

    def test_hash_different(self):
        """Requirements with different names should not be equal."""
        r1 = Requirement(name="a")
        r2 = Requirement(name="b")
        assert r1 != r2


# ── Candidate tests ──────────────────────────────────────────────────────────


class TestCandidate:
    """Test Candidate dataclass."""

    def test_defaults(self):
        """Should default to UNKNOWN status."""
        c = Candidate(name="test", version="1.0.0", object_type=ObjectType.GEM)
        assert c.status == CandidateStatus.UNKNOWN
        assert c.path is None
        assert c.dependencies == []

    def test_local(self):
        """Should store LOCAL status and path."""
        c = Candidate(
            name="test",
            version="1.0.0",
            object_type=ObjectType.GEM,
            status=CandidateStatus.LOCAL,
            path=Path("/test/gem"),
        )
        assert c.status == CandidateStatus.LOCAL
        assert c.path == Path("/test/gem")

    def test_hash_equality(self):
        """Candidates with same name+version should be equal."""
        c1 = Candidate(name="a", version="1.0.0", object_type=ObjectType.GEM)
        c2 = Candidate(name="a", version="1.0.0", object_type=ObjectType.GEM)
        assert c1 == c2
        assert hash(c1) == hash(c2)

    def test_repr(self):
        c = Candidate(
            name="test", version="2.0.0", object_type=ObjectType.ENGINE,
            status=CandidateStatus.REMOTE,
        )
        assert "test" in repr(c)
        assert "2.0.0" in repr(c)
        assert "remote" in repr(c)


# ── SolveResult tests ────────────────────────────────────────────────────────


class TestSolveResult:
    """Test SolveResult dataclass."""

    def test_empty_result(self):
        """An empty result with no conflict should be resolved."""
        r = SolveResult(root_name="test", root_version="1.0.0")
        assert r.is_resolved
        assert r.local_count == 0
        assert r.remote_count == 0
        assert r.unknown_count == 0

    def test_conflict(self):
        """A result with a conflict message should not be resolved."""
        r = SolveResult(
            root_name="test",
            root_version="1.0.0",
            conflict_message="Conflict!",
        )
        assert not r.is_resolved

    def test_counts(self):
        """Should correctly count candidates by status."""
        r = SolveResult(
            root_name="root",
            root_version="1.0.0",
            candidates={
                "a": Candidate(name="a", version="1.0.0", object_type=ObjectType.GEM, status=CandidateStatus.LOCAL),
                "b": Candidate(name="b", version="1.0.0", object_type=ObjectType.GEM, status=CandidateStatus.REMOTE),
                "c": Candidate(name="c", version="1.0.0", object_type=ObjectType.GEM, status=CandidateStatus.REMOTE),
                "d": Candidate(name="d", version="1.0.0", object_type=ObjectType.GEM, status=CandidateStatus.UNKNOWN),
            },
        )
        assert r.local_count == 1
        assert r.remote_count == 2
        assert r.unknown_count == 1


# ── O3DEProvider tests ────────────────────────────────────────────────────────


class TestO3DEProvider:
    """Test the resolvelib Provider adapter."""

    def test_identify(self):
        """Should return the name of a requirement/candidate."""
        resolver = _make_resolver()
        provider = O3DEProvider(resolver)

        req = Requirement(name="org.o3de.gem.test")
        assert provider.identify(req) == "org.o3de.gem.test"

        cand = Candidate(name="foo", version="1.0.0", object_type=ObjectType.GEM)
        assert provider.identify(cand) == "foo"

    def test_find_matches_local(self):
        """Should find local objects matching a requirement."""
        gem = _make_resolved("org.o3de.gem.test", version="1.0.0")
        resolver = _make_resolver(gem)
        provider = O3DEProvider(resolver)

        matches = provider.find_matches(
            identifier="org.o3de.gem.test",
            requirements={"org.o3de.gem.test": [Requirement(name="org.o3de.gem.test")]},
            incompatibilities={},
        )
        assert len(matches) == 1
        assert matches[0].name == "org.o3de.gem.test"
        assert matches[0].status == CandidateStatus.LOCAL

    def test_find_matches_excludes_incompatible(self):
        """Should exclude candidates that don't match version constraints."""
        gem = _make_resolved("gem", version="1.0.0")
        resolver = _make_resolver(gem)
        provider = O3DEProvider(resolver)

        from packaging.specifiers import SpecifierSet
        req = Requirement(name="gem", specifier=SpecifierSet(">=2.0.0"))
        matches = provider.find_matches(
            identifier="gem",
            requirements={"gem": [req]},
            incompatibilities={},
        )
        assert len(matches) == 0

    def test_find_matches_sorted_newest_first(self):
        """When store has multiple versions, they should be newest-first."""
        resolver = _make_resolver()  # no local
        store = MagicMock()
        store.versions = {
            "gem:test": {
                "1.0.0": MagicMock(),
                "2.0.0": MagicMock(),
                "1.5.0": MagicMock(),
            }
        }

        provider = O3DEProvider(resolver, store)
        matches = provider.find_matches(
            identifier="test",
            requirements={"test": [Requirement(name="test")]},
            incompatibilities={},
        )
        assert len(matches) == 3
        assert matches[0].version == "2.0.0"
        assert matches[1].version == "1.5.0"
        assert matches[2].version == "1.0.0"

    def test_is_satisfied_by(self):
        """Should check name + version specifier."""
        resolver = _make_resolver()
        provider = O3DEProvider(resolver)

        req = Requirement.from_specifier("test>=1.0.0")
        c_ok = Candidate(name="test", version="1.5.0", object_type=ObjectType.GEM)
        c_bad = Candidate(name="test", version="0.5.0", object_type=ObjectType.GEM)
        c_wrong = Candidate(name="other", version="2.0.0", object_type=ObjectType.GEM)

        assert provider.is_satisfied_by(req, c_ok)
        assert not provider.is_satisfied_by(req, c_bad)
        assert not provider.is_satisfied_by(req, c_wrong)

    def test_get_dependencies(self):
        """Should convert candidate dependencies to Requirements."""
        resolver = _make_resolver()
        provider = O3DEProvider(resolver)

        cand = Candidate(
            name="root", version="1.0.0", object_type=ObjectType.ENGINE,
            dependencies=["org.o3de.gem.atom>=1.0.0", "org.o3de.gem.physx"],
        )
        reqs = provider.get_dependencies(cand)
        assert len(reqs) == 2
        assert reqs[0].name == "org.o3de.gem.atom"
        assert reqs[1].name == "org.o3de.gem.physx"


# ── O3DEReporter tests ───────────────────────────────────────────────────────


class TestO3DEReporter:
    """Test the resolvelib Reporter adapter."""

    def test_callback(self):
        """Should forward events to the callback."""
        messages: list[str] = []
        reporter = O3DEReporter(callback=messages.append)

        reporter.starting()
        reporter.starting_round(1)
        reporter.ending(None)

        assert len(messages) == 3
        assert "Starting" in messages[0]
        assert "round 1" in messages[1]
        assert "complete" in messages[2]

    def test_no_callback(self):
        """Should work silently with no callback."""
        reporter = O3DEReporter()
        reporter.starting()
        reporter.starting_round(1)
        reporter.ending(None)  # no error


# ── solve_for_workspace tests ────────────────────────────────────────────────


class TestSolveForWorkspace:
    """Test the top-level solve function."""

    def test_missing_root(self):
        """Should return conflict if root not found."""
        resolver = _make_resolver()  # empty
        result = solve_for_workspace("nonexistent", resolver)
        assert not result.is_resolved
        assert "not found" in result.conflict_message

    def test_simple_no_deps(self):
        """Root with no dependencies should resolve to just itself."""
        engine = _make_resolved(
            "org.o3de.engine.core",
            version="2.0.0",
            object_type=ObjectType.ENGINE,
        )
        resolver = _make_resolver(engine)
        result = solve_for_workspace("org.o3de.engine.core", resolver)

        assert result.is_resolved
        assert result.root_name == "org.o3de.engine.core"
        assert result.root_version == "2.0.0"
        assert "org.o3de.engine.core" in result.candidates
        assert result.local_count == 1

    def test_one_dependency(self):
        """Root with one dep should resolve both."""
        gem = _make_resolved("org.o3de.gem.physx", version="1.0.0")
        engine = _make_resolved(
            "org.o3de.engine.core",
            version="2.0.0",
            object_type=ObjectType.ENGINE,
            deps=["org.o3de.gem.physx"],
        )
        resolver = _make_resolver(engine, gem)
        result = solve_for_workspace("org.o3de.engine.core", resolver)

        assert result.is_resolved
        assert len(result.candidates) == 2
        assert "org.o3de.gem.physx" in result.candidates
        assert result.candidates["org.o3de.gem.physx"].status == CandidateStatus.LOCAL

    def test_transitive_deps(self):
        """Should resolve transitive dependencies."""
        gem_c = _make_resolved("c", version="1.0.0")
        gem_b = _make_resolved("b", version="1.0.0", deps=["c"])
        engine = _make_resolved(
            "root",
            version="1.0.0",
            object_type=ObjectType.ENGINE,
            deps=["b"],
        )
        resolver = _make_resolver(engine, gem_b, gem_c)
        result = solve_for_workspace("root", resolver)

        assert result.is_resolved
        assert len(result.candidates) == 3
        assert "c" in result.candidates

    def test_children_separated(self):
        """Children of the root should be in children, not candidates."""
        child_gem = _make_resolved("child_gem", version="1.0.0")
        engine = _make_resolved(
            "root",
            version="1.0.0",
            object_type=ObjectType.ENGINE,
            children=[child_gem],
        )
        resolver = _make_resolver(engine)
        result = solve_for_workspace("root", resolver)

        assert result.is_resolved
        assert "child_gem" not in result.candidates
        assert "child_gem" in result.children
        assert result.children["child_gem"].status == CandidateStatus.LOCAL

    def test_progress_callback(self):
        """Should invoke the progress callback during solving."""
        engine = _make_resolved(
            "root", version="1.0.0", object_type=ObjectType.ENGINE,
        )
        resolver = _make_resolver(engine)
        messages: list[str] = []
        result = solve_for_workspace("root", resolver, progress_callback=messages.append)

        assert result.is_resolved
        assert len(messages) > 0  # at least "Starting..." and "Resolution complete"

    def test_overlays_matched(self):
        """Overlays should be matched to resolved candidates."""
        gem = _make_resolved("org.o3de.gem.test", version="1.0.0")
        engine = _make_resolved(
            "root",
            version="1.0.0",
            object_type=ObjectType.ENGINE,
            deps=["org.o3de.gem.test"],
        )

        overlay = ResolvedObject(
            path=Path("/test/overlay"),
            object_type=ObjectType.GEM,
            name="org.o3de.gem.test.restricted",
            version="1.0.0",
            data={"extends": "org.o3de.gem.test", "precedence": 10},
        )

        resolver = _make_resolver(engine, gem)
        resolver.overlays = {"org.o3de.gem.test.restricted": overlay}

        result = solve_for_workspace("root", resolver)
        assert result.is_resolved
        assert "org.o3de.gem.test" in result.overlays
        assert len(result.overlays["org.o3de.gem.test"]) == 1
        assert result.overlays["org.o3de.gem.test"][0].name == "org.o3de.gem.test.restricted"

    def test_overlay_precedence_order(self):
        """Overlays should be sorted by precedence (ascending)."""
        gem = _make_resolved("base", version="1.0.0")
        engine = _make_resolved(
            "root", version="1.0.0", object_type=ObjectType.ENGINE,
            deps=["base"],
        )

        ov_high = ResolvedObject(
            path=Path("/test/ov_high"),
            object_type=ObjectType.GEM, name="ov_high", version="1.0.0",
            data={"extends": "base", "precedence": 50},
        )
        ov_low = ResolvedObject(
            path=Path("/test/ov_low"),
            object_type=ObjectType.GEM, name="ov_low", version="1.0.0",
            data={"extends": "base", "precedence": 10},
        )

        resolver = _make_resolver(engine, gem)
        resolver.overlays = {"ov_high": ov_high, "ov_low": ov_low}

        result = solve_for_workspace("root", resolver)
        assert result.is_resolved
        overlay_list = result.overlays["base"]
        assert len(overlay_list) == 2
        assert overlay_list[0].precedence < overlay_list[1].precedence


# ── OverlayEntry tests ───────────────────────────────────────────────────────


class TestOverlayEntry:
    """Test OverlayEntry dataclass."""

    def test_defaults(self):
        """Should default to LOCAL status and precedence 0."""
        e = OverlayEntry(name="test", version="1.0.0", extends="base", extends_version=None)
        assert e.status == CandidateStatus.LOCAL
        assert e.precedence == 0

    def test_with_path(self):
        e = OverlayEntry(
            name="ov", version="1.0.0", extends="base",
            extends_version=">=1.0.0", path=Path("/ov"),
        )
        assert e.path == Path("/ov")
        assert e.extends_version == ">=1.0.0"


# ── Remote transitive dependency tests (J6) ──────────────────────────────────


class TestRemoteTransitiveDeps:
    """Test that remote candidates expose dependencies for transitive solving."""

    def test_remote_deps_from_store(self):
        """Remote candidate should carry dependencies from RemoteObject."""
        resolver = _make_resolver()  # no local

        remote_a = MagicMock()
        remote_a.dependencies = ["org.o3de.gem.b>=1.0.0"]

        store = MagicMock()
        store.versions = {
            "gem:org.o3de.gem.a": {"1.0.0": remote_a},
        }

        provider = O3DEProvider(resolver, store)
        matches = provider.find_matches(
            identifier="org.o3de.gem.a",
            requirements={"org.o3de.gem.a": [Requirement(name="org.o3de.gem.a")]},
            incompatibilities={},
        )
        assert len(matches) == 1
        assert matches[0].dependencies == ["org.o3de.gem.b>=1.0.0"]

    def test_remote_deps_generate_requirements(self):
        """get_dependencies should turn remote dep strings into Requirements."""
        resolver = _make_resolver()

        remote_a = MagicMock()
        remote_a.dependencies = ["dep_b>=2.0.0", "dep_c"]

        store = MagicMock()
        store.versions = {
            "gem:gem_a": {"1.0.0": remote_a},
        }

        provider = O3DEProvider(resolver, store)
        matches = provider.find_matches(
            identifier="gem_a",
            requirements={"gem_a": [Requirement(name="gem_a")]},
            incompatibilities={},
        )
        reqs = provider.get_dependencies(matches[0])
        assert len(reqs) == 2
        assert reqs[0].name == "dep_b"
        assert reqs[1].name == "dep_c"

    def test_remote_no_deps_attr_defaults_empty(self):
        """If remote object has no dependencies attr, defaults to empty."""
        resolver = _make_resolver()

        remote_obj = MagicMock(spec=[])  # spec=[] means no auto-created attrs

        store = MagicMock()
        store.versions = {
            "gem:gem_x": {"1.0.0": remote_obj},
        }

        provider = O3DEProvider(resolver, store)
        matches = provider.find_matches(
            identifier="gem_x",
            requirements={"gem_x": [Requirement(name="gem_x")]},
            incompatibilities={},
        )
        assert len(matches) == 1
        assert matches[0].dependencies == []

    def test_remote_transitive_full_solve(self):
        """Full solve: root depends on local A, A depends on remote B (with deps on remote C)."""
        # Local: root engine depends on gem_a
        gem_a = _make_resolved("gem_a", version="1.0.0", deps=["gem_b>=1.0.0"])
        engine = _make_resolved(
            "root", version="1.0.0", object_type=ObjectType.ENGINE, deps=["gem_a"],
        )
        resolver = _make_resolver(engine, gem_a)

        # Remote: gem_b depends on gem_c (transitive)
        remote_b = MagicMock()
        remote_b.dependencies = ["gem_c"]
        remote_c = MagicMock()
        remote_c.dependencies = []

        store = MagicMock()
        store.versions = {
            "gem:gem_b": {"1.0.0": remote_b},
            "gem:gem_c": {"2.0.0": remote_c},
        }

        result = solve_for_workspace("root", resolver, store=store)

        assert result.is_resolved
        assert "gem_a" in result.candidates
        assert "gem_b" in result.candidates
        assert "gem_c" in result.candidates
        assert result.candidates["gem_b"].status == CandidateStatus.REMOTE
        assert result.candidates["gem_c"].status == CandidateStatus.REMOTE
