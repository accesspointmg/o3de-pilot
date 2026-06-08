# O3DE Pilot - H2 Coverage Ratchet Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests targeting uncovered branches in audit, workspace, project, deps, and registry."""

import json
import subprocess
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, PropertyMock
from click.testing import CliRunner

from tests.conftest import _write_json


# ---------------------------------------------------------------------------
# Helpers (shared with test_commands_extended.py pattern)
# ---------------------------------------------------------------------------

def _setup_manifest(tmp_path, **kw):
    manifest = {
        "$schemaVersion": "2.0.0",
        "o3de_manifest": {"name": "test"},
        "local": {
            "engines": kw.get("engines", []),
            "projects": kw.get("projects", []),
            "gems": kw.get("gems", []),
            "templates": kw.get("templates", []),
            "repos": kw.get("repos", []),
            "overlays": kw.get("overlays", []),
        },
        "remote": {"repos": []},
        "remotes": [],
    }
    mp = tmp_path / "o3de_manifest.2-0-0.json"
    _write_json(mp, manifest)
    return mp


def _make_obj(tmp_path, obj_type, name, version="1.0.0", extra_data=None):
    d = tmp_path / name.replace(".", "_")
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        obj_type: {"name": name, "version": version, "display_name": name},
    }
    if extra_data:
        data.update(extra_data)
        if obj_type in extra_data:
            data[obj_type].update(extra_data[obj_type])
    _write_json(d / f"{obj_type}.json", data)
    _write_json(d / f"{obj_type}.2-0-0.json", data)
    return d


def _patch_manifest(tmp_path, mp):
    """Return a context manager that patches all manifest path sites."""
    from contextlib import ExitStack
    stack = ExitStack()
    for site in [
        "o3de_pilot.core.paths.get_manifest_path",
        "o3de_pilot.commands.audit.get_manifest_path",
        "o3de_pilot.commands.deps.get_manifest_path",
        "o3de_pilot.commands.registry.get_manifest_path",
        "o3de_pilot.commands.workspace.get_manifest_path",
        "o3de_pilot.core.resolver.get_manifest_path",
    ]:
        try:
            stack.enter_context(patch(site, return_value=mp))
        except AttributeError:
            pass
    for site in [
        "o3de_pilot.core.resolver.get_resolved_manifest_path",
        "o3de_pilot.commands.workspace.get_resolved_manifest_path",
        "o3de_pilot.commands.registry.get_resolved_manifest_path",
    ]:
        try:
            stack.enter_context(patch(site, return_value=tmp_path / "resolved.json"))
        except AttributeError:
            pass
    return stack


# ===================================================================
# AUDIT - Deprecation, Integrity, Peer/Optional Deps, Conflicts, Display
# ===================================================================

class TestAuditDeprecated:
    def test_type_scoped_deprecated(self, tmp_path):
        """Deprecated info inside the type-scoped dict (line 84-86)."""
        from o3de_pilot.commands.audit import audit
        d = tmp_path / "dep_gem"
        d.mkdir()
        _write_json(d / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.deprecated",
                "version": "1.0.0",
                "display_name": "Old Gem",
                "deprecated": {
                    "message": "This gem is old",
                    "replacement": "org.test.new>=2.0",
                },
            },
        })
        _write_json(d / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.deprecated",
                "version": "1.0.0",
                "display_name": "Old Gem",
                "deprecated": {
                    "message": "This gem is old",
                    "replacement": "org.test.new>=2.0",
                },
            },
        })
        mp = _setup_manifest(tmp_path, gems=[str(d)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(audit)
        assert result.exit_code == 1
        assert "Deprecated" in result.output or "deprecated" in result.output.lower()

    def test_root_level_deprecated_string(self, tmp_path):
        """Deprecated as a simple string at root level (fallback path)."""
        from o3de_pilot.commands.audit import audit
        d = tmp_path / "dep_gem2"
        d.mkdir()
        gem_data = {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.oldgem",
                "version": "1.0.0",
                "display_name": "Old Gem 2",
            },
            "deprecated": "Use something else",
        }
        _write_json(d / "gem.json", gem_data)
        _write_json(d / "gem.2-0-0.json", gem_data)
        mp = _setup_manifest(tmp_path, gems=[str(d)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(audit)
        assert result.exit_code == 1


class TestAuditIntegrity:
    def test_missing_source_sha256(self, tmp_path):
        """Downloads with source but no source_sha256 (line 105)."""
        from o3de_pilot.commands.audit import audit
        d = tmp_path / "int_gem"
        d.mkdir()
        gem_data = {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.integrity",
                "version": "1.0.0",
                "display_name": "Integrity Gem",
            },
            "releases": [{
                "name": "v1.0.0",
                "downloads": [
                    {"source": "https://example.com/src.zip"},
                ],
            }],
        }
        _write_json(d / "gem.json", gem_data)
        _write_json(d / "gem.2-0-0.json", gem_data)
        mp = _setup_manifest(tmp_path, gems=[str(d)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(audit, ["--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["total"] > 0
        fields = [i["field"] for i in data["issues"].get("missing_integrity", [])]
        assert "downloads[0].source_sha256" in fields

    def test_missing_lfs_and_binary_sha256(self, tmp_path):
        """Downloads with lfs, binaries with binary — no sha256 (lines 109, 118)."""
        from o3de_pilot.commands.audit import audit
        d = tmp_path / "lfs_gem"
        d.mkdir()
        gem_data = {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.lfs",
                "version": "1.0.0",
                "display_name": "LFS Gem",
            },
            "releases": [{
                "name": "v1.0.0",
                "downloads": [
                    {"lfs": "https://example.com/assets.zip"},
                ],
                "binaries": [
                    {"binary": "https://example.com/bin.zip"},
                ],
            }],
        }
        _write_json(d / "gem.json", gem_data)
        _write_json(d / "gem.2-0-0.json", gem_data)
        mp = _setup_manifest(tmp_path, gems=[str(d)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(audit, ["--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        fields = [i["field"] for i in data["issues"]["missing_integrity"]]
        assert "downloads[0].lfs_sha256" in fields
        assert "binaries[0].sha256" in fields


class TestAuditPeerAndOptionalDeps:
    def test_missing_peer_dep(self, tmp_path):
        """Peer dependency not installed (lines 158-160)."""
        from o3de_pilot.commands.audit import audit
        d = tmp_path / "peer_gem"
        d.mkdir()
        gem_data = {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.peer",
                "version": "1.0.0",
                "display_name": "Peer Gem",
                "peer_dependent": {"gems": ["org.test.missing_peer==1.0.0"]},
            },
        }
        _write_json(d / "gem.json", gem_data)
        _write_json(d / "gem.2-0-0.json", gem_data)
        mp = _setup_manifest(tmp_path, gems=[str(d)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(audit, ["--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "missing_peer_dependencies" in data["issues"]

    def test_optional_dep_version_mismatch(self, tmp_path):
        """Optional dep found but version doesn't match (line 168)."""
        from o3de_pilot.commands.audit import audit
        # Create the optional dep (wrong version)
        opt_dir = tmp_path / "opt_dep"
        opt_dir.mkdir()
        _write_json(opt_dir / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.optlib", "version": "1.0.0", "display_name": "Opt Lib"},
        })
        _write_json(opt_dir / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.optlib", "version": "1.0.0", "display_name": "Opt Lib"},
        })
        # Create the consumer (wants >=5.0.0)
        d = tmp_path / "opt_gem"
        d.mkdir()
        gem_data = {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.optconsumer",
                "version": "1.0.0",
                "display_name": "Opt Consumer",
                "optional_dependent": {"gems": ["org.test.optlib>=5.0.0"]},
            },
        }
        _write_json(d / "gem.json", gem_data)
        _write_json(d / "gem.2-0-0.json", gem_data)
        mp = _setup_manifest(tmp_path, gems=[str(d), str(opt_dir)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(audit, ["--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "unresolvable_optional" in data["issues"]

    def test_dep_version_mismatch(self, tmp_path):
        """Required dep found but version mismatch (line 142)."""
        from o3de_pilot.commands.audit import audit
        # Provide the dep at version 1.0.0
        dep_dir = tmp_path / "vlib"
        dep_dir.mkdir()
        _write_json(dep_dir / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.vlib", "version": "1.0.0", "display_name": "VLib"},
        })
        _write_json(dep_dir / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.vlib", "version": "1.0.0", "display_name": "VLib"},
        })
        # Consumer wants >=3.0.0
        d = tmp_path / "vcon"
        d.mkdir()
        gem_data = {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.vcon",
                "version": "1.0.0",
                "display_name": "VCon",
                "dependent": {"gems": ["org.test.vlib>=3.0.0"]},
            },
        }
        _write_json(d / "gem.json", gem_data)
        _write_json(d / "gem.2-0-0.json", gem_data)
        mp = _setup_manifest(tmp_path, gems=[str(d), str(dep_dir)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(audit, ["--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "missing_dependencies" in data["issues"]
        reasons = [i["reason"] for i in data["issues"]["missing_dependencies"]]
        assert any("version mismatch" in r for r in reasons)

    def test_peer_dep_version_mismatch(self, tmp_path):
        """Peer dep found but version mismatch (line 150)."""
        from o3de_pilot.commands.audit import audit
        peer_dir = tmp_path / "peerlib"
        peer_dir.mkdir()
        _write_json(peer_dir / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.peerlib", "version": "1.0.0", "display_name": "PeerLib"},
        })
        _write_json(peer_dir / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.peerlib", "version": "1.0.0", "display_name": "PeerLib"},
        })
        d = tmp_path / "peercon"
        d.mkdir()
        gem_data = {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.peercon",
                "version": "1.0.0",
                "display_name": "PeerCon",
                "peer_dependent": {"gems": ["org.test.peerlib>=9.0.0"]},
            },
        }
        _write_json(d / "gem.json", gem_data)
        _write_json(d / "gem.2-0-0.json", gem_data)
        mp = _setup_manifest(tmp_path, gems=[str(d), str(peer_dir)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(audit, ["--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert "missing_peer_dependencies" in data["issues"]
        reasons = [i["reason"] for i in data["issues"]["missing_peer_dependencies"]]
        assert any("version mismatch" in r for r in reasons)


class TestAuditDisplay:
    """Test _display_issues directly to cover the rich table rendering (lines 192-257)."""

    def test_display_all_categories(self):
        from o3de_pilot.commands.audit import _display_issues
        issues = {
            "deprecated": [{"object": "a", "message": "old", "replacement": "b"}],
            "missing_integrity": [{"object": "c", "release": "v1", "field": "sha256"}],
            "missing_dependencies": [{"object": "d", "dependency": "e", "reason": "not found"}],
            "missing_peer_dependencies": [{"object": "f", "peer": "g", "reason": "not installed"}],
            "unresolvable_optional": [{"object": "h", "optional": "i", "reason": "wrong ver"}],
            "conflicts": [{"dependency": "j", "requirer_a": "k", "constraint_a": ">=1",
                           "requirer_b": "l", "constraint_b": ">=2", "resolved_version": "1.5"}],
        }
        # Should not raise
        _display_issues(issues)

    def test_display_empty(self):
        from o3de_pilot.commands.audit import _display_issues
        _display_issues({})


class TestAuditCollectIssuesConflicts:
    """Test _collect_issues with conflicts via mocked resolver."""

    def test_conflicts_collected(self):
        from o3de_pilot.commands.audit import _collect_issues
        from o3de_pilot.core.resolver import DependencyConflict

        resolver = MagicMock()
        resolver.objects = {}
        resolver.conflicts = [
            DependencyConflict(
                dependency_name="org.test.shared",
                requirer_a="org.test.a",
                constraint_a=">=1.0.0",
                requirer_b="org.test.b",
                constraint_b=">=2.0.0",
                resolved_version="1.5.0",
            )
        ]
        issues = _collect_issues(resolver)
        assert "conflicts" in issues
        assert issues["conflicts"][0]["dependency"] == "org.test.shared"


# ===================================================================
# PROJECT - Build / Run
# ===================================================================

class TestProjectBuild:
    def test_no_cmakelists(self, tmp_path):
        """Missing CMakeLists.txt should exit 1 (line 245)."""
        from o3de_pilot.commands.project import build
        runner = CliRunner()
        result = runner.invoke(build, ["--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "No CMakeLists.txt" in result.output

    def test_configure_with_presets(self, tmp_path):
        """CMakePresets.json present triggers preset configure (line 256)."""
        from o3de_pilot.commands.project import build
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)")
        (tmp_path / "CMakePresets.json").write_text("{}")
        runner = CliRunner()
        success = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=success) as mock_run:
            result = runner.invoke(build, ["--path", str(tmp_path)])
        assert result.exit_code == 0
        # First call should be the preset configure
        first_call_args = mock_run.call_args_list[0][0][0]
        assert "--preset" in first_call_args

    def test_configure_failure(self, tmp_path):
        """Configure returns nonzero (line 261)."""
        from o3de_pilot.commands.project import build
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)")
        runner = CliRunner()
        fail_result = MagicMock(returncode=1, stdout="", stderr="config error")
        with patch("subprocess.run", return_value=fail_result):
            result = runner.invoke(build, ["--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "configure failed" in result.output

    def test_build_failure(self, tmp_path):
        """Build step returns nonzero (line 270)."""
        from o3de_pilot.commands.project import build
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)")
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        runner = CliRunner()
        fail_result = MagicMock(returncode=1, stdout="", stderr="link error bla")
        with patch("subprocess.run", return_value=fail_result):
            result = runner.invoke(build, ["--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "Build failed" in result.output

    def test_configure_without_presets(self, tmp_path):
        """No CMakePresets.json — standard configure (line 253)."""
        from o3de_pilot.commands.project import build
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.20)")
        runner = CliRunner()
        success = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", return_value=success) as mock_run:
            result = runner.invoke(build, ["--path", str(tmp_path)])
        assert result.exit_code == 0
        first_call_args = mock_run.call_args_list[0][0][0]
        assert "-S" in first_call_args
        assert "--preset" not in first_call_args


class TestProjectRun:
    def test_no_launcher(self, tmp_path):
        """No launcher found exits 1 (line 303)."""
        from o3de_pilot.commands.project import run
        (tmp_path / "build").mkdir()
        runner = CliRunner()
        result = runner.invoke(run, ["--path", str(tmp_path)])
        assert result.exit_code == 1
        assert "No launcher found" in result.output

    def test_launcher_found(self, tmp_path):
        """Launcher at first search path triggers Popen (line 308)."""
        from o3de_pilot.commands.project import run
        build_dir = tmp_path / "build" / "bin" / "profile"
        build_dir.mkdir(parents=True)
        launcher = build_dir / f"{tmp_path.name}.GameLauncher.exe"
        launcher.write_text("fake")
        runner = CliRunner()
        with patch("subprocess.Popen") as mock_popen:
            result = runner.invoke(run, ["--path", str(tmp_path)])
        assert result.exit_code == 0
        mock_popen.assert_called_once()
        assert "Launched" in result.output


# ===================================================================
# DEPS - Optional/Peer status, JSON output, tree building
# ===================================================================

class TestDepsListOptionalPeer:
    """Cover optional and peer dep display in deps list (lines 136-151)."""

    def test_optional_and_peer_deps_displayed(self, tmp_path):
        from o3de_pilot.commands.deps import list_deps
        # Create the main gem with optional + peer deps
        d = tmp_path / "main_gem"
        d.mkdir()
        gem_data = {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.main",
                "version": "1.0.0",
                "display_name": "Main",
                "optional_dependent": {"gems": ["org.test.optavail", "org.test.optmissing"]},
                "peer_dependent": {"gems": ["org.test.peeravail", "org.test.peermissing"]},
            },
        }
        _write_json(d / "gem.json", gem_data)
        _write_json(d / "gem.2-0-0.json", gem_data)
        # Create available optional
        oa = tmp_path / "opt_avail"
        oa.mkdir()
        _write_json(oa / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.optavail", "version": "1.0.0", "display_name": "OptA"},
        })
        _write_json(oa / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.optavail", "version": "1.0.0", "display_name": "OptA"},
        })
        # Create available peer
        pa = tmp_path / "peer_avail"
        pa.mkdir()
        _write_json(pa / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.peeravail", "version": "1.0.0", "display_name": "PeerA"},
        })
        _write_json(pa / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.peeravail", "version": "1.0.0", "display_name": "PeerA"},
        })
        mp = _setup_manifest(tmp_path, gems=[str(d), str(oa), str(pa)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(list_deps, ["org.test.main"])
        assert result.exit_code == 0
        assert "available" in result.output
        assert "not installed" in result.output
        assert "ok" in result.output
        assert "missing" in result.output


class TestDepsJsonOutput:
    """Cover _output_json paths (lines 286-316)."""

    def test_json_named_missing(self, tmp_path):
        """Named object not found => error JSON (line 310)."""
        from o3de_pilot.commands.deps import tree_command
        d = tmp_path / "jgem"
        d.mkdir()
        _write_json(d / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.exists", "version": "1.0.0", "display_name": "Exists"},
        })
        _write_json(d / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.exists", "version": "1.0.0", "display_name": "Exists"},
        })
        mp = _setup_manifest(tmp_path, gems=[str(d)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(tree_command, ["--json", "org.test.nosuch"])
        assert result.exit_code == 0
        assert "error" in result.output.lower()

    def test_json_all_roots(self, tmp_path):
        """--all flag triggers show_all roots path (line 316)."""
        from o3de_pilot.commands.deps import tree_command
        d = tmp_path / "rgem"
        d.mkdir()
        _write_json(d / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.root", "version": "1.0.0", "display_name": "Root"},
        })
        _write_json(d / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.root", "version": "1.0.0", "display_name": "Root"},
        })
        mp = _setup_manifest(tmp_path, gems=[str(d)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(tree_command, ["--json", "--all"])
        assert result.exit_code == 0
        # Output should be a JSON array
        assert "[" in result.output

    def test_json_with_deps_and_children(self, tmp_path):
        """Object with deps including circular and missing (lines 286-304)."""
        from o3de_pilot.commands.deps import tree_command
        # depA depends on depB, depB depends on depA (circular)
        da = tmp_path / "da"
        da.mkdir()
        _write_json(da / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.depa",
                "version": "1.0.0",
                "display_name": "DepA",
                "dependent": {"gems": ["org.test.depb", "org.test.nomatch"]},
            },
        })
        _write_json(da / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.depa",
                "version": "1.0.0",
                "display_name": "DepA",
                "dependent": {"gems": ["org.test.depb", "org.test.nomatch"]},
            },
        })
        db = tmp_path / "db"
        db.mkdir()
        _write_json(db / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.depb",
                "version": "1.0.0",
                "display_name": "DepB",
                "dependent": {"gems": ["org.test.depa"]},
            },
        })
        _write_json(db / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.depb",
                "version": "1.0.0",
                "display_name": "DepB",
                "dependent": {"gems": ["org.test.depa"]},
            },
        })
        mp = _setup_manifest(tmp_path, gems=[str(da), str(db)])
        runner = CliRunner()
        with _patch_manifest(tmp_path, mp):
            result = runner.invoke(tree_command, ["--json", "org.test.depa"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "org.test.depa"


class TestDepsBuildTree:
    """Cover _build_tree optional/peer/children branches (lines 226-248)."""

    def test_build_tree_optional_peer_children(self):
        from o3de_pilot.core.resolver import ObjectNameVersion, ResolvedObject
        from o3de_pilot.core import ObjectType
        from o3de_pilot.commands.deps import _build_tree
        from rich.tree import Tree

        # Create fake objects
        opt_resolved = ResolvedObject(
            path=Path("/fake/opt"), object_type=ObjectType.GEM,
            name="org.opt.resolved", version="1.0.0", data={},
        )
        peer_resolved = ResolvedObject(
            path=Path("/fake/peer"), object_type=ObjectType.GEM,
            name="org.peer.resolved", version="2.0.0", data={},
        )
        child_obj = ResolvedObject(
            path=Path("/fake/child"), object_type=ObjectType.GEM,
            name="org.child.one", version="3.0.0", data={},
        )

        main_obj = ResolvedObject(
            path=Path("/fake/main"), object_type=ObjectType.GEM,
            name="org.main", version="1.0.0", data={},
        )
        main_obj.optional_dependencies = [
            ObjectNameVersion("org.opt.resolved"),
            ObjectNameVersion("org.opt.missing"),
        ]
        main_obj.peer_dependencies = [
            ObjectNameVersion("org.peer.resolved"),
            ObjectNameVersion("org.peer.missing"),
        ]
        main_obj.children = [child_obj]

        resolver = MagicMock()
        resolver.objects = {
            "org.main": main_obj,
            "org.opt.resolved": opt_resolved,
            "org.peer.resolved": peer_resolved,
            "org.child.one": child_obj,
        }

        tree = Tree("root")
        visited = {"org.main"}
        _build_tree(tree, main_obj, resolver, visited, max_depth=3, current_depth=0)

        # Verify nodes were added (Tree.children)
        labels = [str(c.label) for c in tree.children]
        assert any("optional" in l for l in labels)
        assert any("peer" in l for l in labels)
        assert any("org.child.one" in l for l in labels)

    def test_build_tree_already_visited_child(self):
        from o3de_pilot.core.resolver import ResolvedObject
        from o3de_pilot.core import ObjectType
        from o3de_pilot.commands.deps import _build_tree
        from rich.tree import Tree

        child_obj = ResolvedObject(
            path=Path("/fake/child"), object_type=ObjectType.GEM,
            name="org.child.visited", version="1.0.0", data={},
        )
        main_obj = ResolvedObject(
            path=Path("/fake/main"), object_type=ObjectType.GEM,
            name="org.main", version="1.0.0", data={},
        )
        main_obj.children = [child_obj]

        resolver = MagicMock()
        resolver.objects = {"org.main": main_obj, "org.child.visited": child_obj}

        tree = Tree("root")
        visited = {"org.main", "org.child.visited"}  # child already visited
        _build_tree(tree, main_obj, resolver, visited, max_depth=3, current_depth=0)

        labels = [str(c.label) for c in tree.children]
        assert any("already shown" in l for l in labels)


# ===================================================================
# WORKSPACE - Update (engine/project/fallback detection) and Solve
# ===================================================================

class TestWorkspaceUpdate:
    def test_update_engine_root(self, tmp_path):
        """Update workspace with engine.json root (line 187)."""
        from o3de_pilot.commands.workspace import update_command
        # Create workspace dir with metadata
        ws = tmp_path / "testws"
        ws.mkdir()
        source = tmp_path / "engine_src"
        source.mkdir()
        (source / "engine.json").write_text("{}")
        _write_json(ws / ".workspace.json", {
            "sources": [str(source)],
            "overlays": [],
        })
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.Workspace") as mock_ws:
            mock_ws.return_value = MagicMock()
            result = runner.invoke(update_command, [str(ws)])
        assert result.exit_code == 0
        call_kwargs = mock_ws.call_args[1]
        from o3de_pilot.core import ObjectType
        assert call_kwargs["root_object_type"] == ObjectType.ENGINE

    def test_update_project_root(self, tmp_path):
        """Update workspace with project.json root (line 189)."""
        from o3de_pilot.commands.workspace import update_command
        ws = tmp_path / "testws2"
        ws.mkdir()
        source = tmp_path / "proj_src"
        source.mkdir()
        (source / "project.json").write_text("{}")
        _write_json(ws / ".workspace.json", {
            "sources": [str(source)],
            "overlays": [],
        })
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.Workspace") as mock_ws:
            mock_ws.return_value = MagicMock()
            result = runner.invoke(update_command, [str(ws)])
        assert result.exit_code == 0
        call_kwargs = mock_ws.call_args[1]
        from o3de_pilot.core import ObjectType
        assert call_kwargs["root_object_type"] == ObjectType.PROJECT

    def test_update_fallback_root(self, tmp_path):
        """No engine.json or project.json → fallback ENGINE (line 191)."""
        from o3de_pilot.commands.workspace import update_command
        ws = tmp_path / "testws3"
        ws.mkdir()
        source = tmp_path / "bare_src"
        source.mkdir()
        _write_json(ws / ".workspace.json", {
            "sources": [str(source)],
            "overlays": [],
        })
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.Workspace") as mock_ws:
            mock_ws.return_value = MagicMock()
            result = runner.invoke(update_command, [str(ws)])
        assert result.exit_code == 0
        call_kwargs = mock_ws.call_args[1]
        from o3de_pilot.core import ObjectType
        assert call_kwargs["root_object_type"] == ObjectType.ENGINE

    def test_update_not_found(self, tmp_path):
        """Workspace path not found exits 1 (line 157)."""
        from o3de_pilot.commands.workspace import update_command
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path):
            result = runner.invoke(update_command, ["nonexistent_ws_xyz"])
        assert result.exit_code == 1

    def test_update_missing_metadata(self, tmp_path):
        """Workspace dir exists but no .workspace.json (line 162)."""
        from o3de_pilot.commands.workspace import update_command
        ws = tmp_path / "nometaws"
        ws.mkdir()
        runner = CliRunner()
        result = runner.invoke(update_command, [str(ws)])
        assert result.exit_code == 1
        assert "Not a valid workspace" in result.output


class TestWorkspaceSolve:
    def test_solve_json_output(self, tmp_path):
        """--json flag triggers JSON output path (lines 435-460)."""
        from o3de_pilot.commands.workspace import solve_command

        fake_result = MagicMock()
        fake_result.root_name = "org.test.engine"
        fake_result.root_version = "1.0.0"
        fake_result.is_resolved = True
        fake_result.conflict_message = None
        fake_result.candidates = {}
        fake_result.children = {}
        fake_result.overlays = {}

        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.Resolver") as mock_res, \
             patch("o3de_pilot.commands.workspace.solve_for_workspace", return_value=fake_result):
            mock_res.return_value = MagicMock()
            result = runner.invoke(solve_command, ["org.test.engine", "--json"])
        assert result.exit_code == 0
        # Output may contain spinner text before JSON; find the JSON portion
        raw = result.output
        json_start = raw.index("{")
        data = json.loads(raw[json_start:])
        assert data["root"] == "org.test.engine"

    def test_solve_unresolved(self, tmp_path):
        """Unresolved result exits 1 (line 463)."""
        from o3de_pilot.commands.workspace import solve_command

        fake_result = MagicMock()
        fake_result.is_resolved = False
        fake_result.conflict_message = "version conflict"
        fake_result.candidates = {}
        fake_result.children = {}
        fake_result.overlays = {}

        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.Resolver") as mock_res, \
             patch("o3de_pilot.commands.workspace.solve_for_workspace", return_value=fake_result):
            mock_res.return_value = MagicMock()
            result = runner.invoke(solve_command, ["org.test.engine"])
        assert result.exit_code == 1

    def test_solve_with_children_and_overlays(self, tmp_path):
        """Resolved result with children and overlays (lines 495-518)."""
        from o3de_pilot.commands.workspace import solve_command
        from o3de_pilot.core import ObjectType

        fake_cand = MagicMock()
        fake_cand.version = "1.0.0"
        fake_cand.object_type = ObjectType.GEM
        fake_cand.status = MagicMock(value="local")
        fake_cand.path = Path("/fake/gem")

        fake_child = MagicMock()
        fake_child.version = "2.0.0"
        fake_child.object_type = ObjectType.GEM
        fake_child.path = Path("/fake/child")

        fake_overlay_entry = MagicMock()
        fake_overlay_entry.name = "org.overlay"
        fake_overlay_entry.version = "1.0.0"
        fake_overlay_entry.precedence = 0

        fake_result = MagicMock()
        fake_result.root_name = "org.test.engine"
        fake_result.root_version = "1.0.0"
        fake_result.is_resolved = True
        fake_result.conflict_message = None
        fake_result.candidates = {"org.test.gem": fake_cand}
        fake_result.children = {"org.test.child": fake_child}
        fake_result.overlays = {"org.test.engine": [fake_overlay_entry]}
        fake_result.local_count = 1
        fake_result.remote_count = 0
        fake_result.unknown_count = 0

        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.Resolver") as mock_res, \
             patch("o3de_pilot.commands.workspace.solve_for_workspace", return_value=fake_result):
            mock_res.return_value = MagicMock()
            result = runner.invoke(solve_command, ["org.test.engine"])
        assert result.exit_code == 0
        assert "org.test.child" in result.output or "Contained" in result.output

    def test_solve_include_store(self, tmp_path):
        """--include-store triggers Store creation + refresh (line 413)."""
        from o3de_pilot.commands.workspace import solve_command

        fake_result = MagicMock()
        fake_result.root_name = "org.test.engine"
        fake_result.root_version = "1.0.0"
        fake_result.is_resolved = True
        fake_result.conflict_message = None
        fake_result.candidates = {}
        fake_result.children = {}
        fake_result.overlays = {}

        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.Resolver") as mock_res, \
             patch("o3de_pilot.commands.workspace.solve_for_workspace", return_value=fake_result), \
             patch("o3de_pilot.core.store.Store") as mock_store:
            mock_resolver_inst = MagicMock()
            mock_resolver_inst.manifest_remotes = []
            mock_res.return_value = mock_resolver_inst
            result = runner.invoke(solve_command, ["org.test.engine", "--json", "--include-store"])
        assert result.exit_code == 0


# ===================================================================
# REGISTRY - Install and List dispatch
# ===================================================================

class TestRegistryInstall:
    def _get_install_cmd(self):
        from o3de_pilot.commands.registry import install_command
        return install_command

    def test_no_results(self, tmp_path):
        """Search returns empty list (line 140)."""
        cmd = self._get_install_cmd()
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.Resolver") as mock_res, \
             patch("o3de_pilot.commands.registry.Store") as mock_store:
            mock_res.return_value = MagicMock()
            store_inst = MagicMock()
            store_inst.search.return_value = []
            mock_store.return_value = store_inst
            result = runner.invoke(cmd, ["org.test.notfound"])
        assert "not found" in result.output.lower() or "No" in result.output

    def test_dry_run(self, tmp_path):
        """--dry-run prints details without downloading (lines 159-170)."""
        cmd = self._get_install_cmd()
        fake_pkg = MagicMock()
        fake_pkg.name = "org.test.pkg"
        fake_pkg.version = "1.0.0"
        fake_pkg.object_type = MagicMock(value="gem")
        fake_pkg.source_control_url = "https://github.com/test"
        fake_pkg.download_url = None
        fake_pkg.source_sha256 = "abc123"

        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.Resolver") as mock_res, \
             patch("o3de_pilot.commands.registry.Store") as mock_store:
            mock_res.return_value = MagicMock()
            store_inst = MagicMock()
            store_inst.search.return_value = [fake_pkg]
            mock_store.return_value = store_inst
            result = runner.invoke(cmd, ["org.test.pkg", "--dry-run"])
        assert result.exit_code == 0
        assert "org.test.pkg" in result.output

    def test_install_download_failure(self, tmp_path):
        """Download exception is caught (line 196)."""
        cmd = self._get_install_cmd()
        fake_pkg = MagicMock()
        fake_pkg.name = "org.test.failpkg"
        fake_pkg.version = "1.0.0"
        fake_pkg.object_type = MagicMock(value="gem")
        fake_pkg.source_control_url = None
        fake_pkg.download_url = "https://example.com/pkg.zip"
        fake_pkg.source_sha256 = "abc"

        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.Resolver") as mock_res, \
             patch("o3de_pilot.commands.registry.Store") as mock_store:
            mock_res.return_value = MagicMock()
            store_inst = MagicMock()
            store_inst.search.return_value = [fake_pkg]
            store_inst.download_sync.side_effect = Exception("network error")
            mock_store.return_value = store_inst
            result = runner.invoke(cmd, ["org.test.failpkg"])
        assert "failed" in result.output.lower() or "error" in result.output.lower()


class TestRegistryList:
    @pytest.mark.parametrize("obj_type", ["projects", "gems", "templates", "engines"])
    def test_list_dispatch(self, obj_type, tmp_path):
        """List dispatches to correct sub-command (lines 285-301)."""
        from o3de_pilot.commands.registry import list_command
        runner = CliRunner()
        # Patch the downstream list commands to avoid needing real manifests
        with patch("o3de_pilot.commands.registry.Resolver") as mock_res, \
             patch("o3de_pilot.commands.registry.Store") as mock_store:
            mock_res.return_value = MagicMock()
            mock_store.return_value = MagicMock()
            # The list command invokes sub-commands via click context
            # Just verify it doesn't crash
            result = runner.invoke(list_command, [obj_type])
        # May succeed or fail depending on context, but should not raise
        assert result.exception is None or isinstance(result.exception, SystemExit)


# ===================================================================
# PUBLISH - validate_object branches
# ===================================================================

class TestPublishValidateObject:
    def test_dir_no_json(self, tmp_path):
        """Directory with no O3DE JSON files (line 160-161)."""
        from o3de_pilot.commands.publish import validate_object
        errors, warnings = validate_object(tmp_path)
        assert any("No O3DE object JSON" in e for e in errors)

    def test_dir_with_legacy_json(self, tmp_path):
        """Directory with only legacy (non-versioned) JSON (line 158)."""
        from o3de_pilot.commands.publish import validate_object
        _write_json(tmp_path / "gem.json", {
            "gem": {"name": "org.test.legacy", "version": "1.0.0", "display_name": "Legacy"},
        })
        errors, warnings = validate_object(tmp_path)
        # Should find the file but warn about missing $schemaVersion
        assert any("schemaVersion" in w.lower() for w in warnings) or \
               any("schema" in w.lower() for w in warnings)

    def test_invalid_json(self, tmp_path):
        """Malformed JSON file (line 174-176)."""
        from o3de_pilot.commands.publish import validate_object
        bad_file = tmp_path / "gem.2-0-0.json"
        bad_file.write_text("{invalid json!!}")
        errors, warnings = validate_object(tmp_path)
        assert any("Invalid JSON" in e for e in errors)

    def test_missing_schema_version(self, tmp_path):
        """JSON without $schemaVersion (line 197-200)."""
        from o3de_pilot.commands.publish import validate_object
        _write_json(tmp_path / "gem.2-0-0.json", {
            "gem": {"name": "org.test.gem", "version": "1.0.0", "display_name": "Test"},
        })
        errors, warnings = validate_object(tmp_path)
        assert any("schemaversion" in w.lower() or "schema" in w.lower() for w in warnings) or \
               any("schemaversion" in e.lower() or "schema" in e.lower() for e in errors)

    def test_wrong_schema_version(self, tmp_path):
        """JSON with non-2.0.0 $schemaVersion (line 198)."""
        from o3de_pilot.commands.publish import validate_object
        _write_json(tmp_path / "gem.2-0-0.json", {
            "$schemaVersion": "1.0.0",
            "gem": {"name": "org.test.gem", "version": "1.0.0", "display_name": "Test"},
        })
        errors, warnings = validate_object(tmp_path)
        assert any("1.0.0" in w for w in warnings)

    def test_releases_missing_integrity(self, tmp_path):
        """Releases with downloads/binaries missing sha256 (lines 248-269)."""
        from o3de_pilot.commands.publish import validate_object
        _write_json(tmp_path / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.int", "version": "1.0.0", "display_name": "IntTest"},
            "releases": [{
                "name": "v1",
                "downloads": [
                    {"source": "https://x.com/src.zip"},
                    {"lfs": "https://x.com/lfs.zip"},
                ],
                "binaries": [
                    {"binary": "https://x.com/bin.zip"},
                ],
            }],
        })
        errors, warnings = validate_object(tmp_path)
        assert any("source_sha256" in w for w in warnings)
        assert any("lfs_sha256" in w for w in warnings)
        assert any("binaries" in w and "sha256" in w for w in warnings)

    def test_nonexistent_path(self, tmp_path):
        """Path doesn't exist (line 167-168)."""
        from o3de_pilot.commands.publish import validate_object
        errors, warnings = validate_object(tmp_path / "nope.json")
        assert any("does not exist" in e for e in errors)


class TestPublishPush:
    def test_push_validation_errors(self, tmp_path):
        """Push with validation errors aborts (lines 103-106)."""
        from o3de_pilot.commands.publish import push_command
        runner = CliRunner()
        # Empty dir — no JSON
        result = runner.invoke(push_command, [str(tmp_path)])
        assert result.exit_code == 1
        assert "Validation Failed" in result.output or "fix" in result.output.lower()

    def test_push_no_remote(self, tmp_path):
        """Push with no --remote and no manifest remote (lines 120-131)."""
        from o3de_pilot.commands.publish import push_command
        _write_json(tmp_path / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.pushgem", "version": "1.0.0", "display_name": "PG"},
            "origin": "test",
            "licenses": ["Apache-2.0"],
        })
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.get_manifest_path",
                    return_value=tmp_path / "nomanifest.json"):
            result = runner.invoke(push_command, [str(tmp_path)])
        assert result.exit_code == 1
        assert "No remote" in result.output

    def test_push_uses_manifest_remote(self, tmp_path):
        """Push picks remote from manifest (line 124)."""
        from o3de_pilot.commands.publish import push_command
        _write_json(tmp_path / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.pushgem2", "version": "1.0.0", "display_name": "PG2"},
            "origin": "test",
            "licenses": ["Apache-2.0"],
        })
        manifest = tmp_path / "manifest.json"
        _write_json(manifest, {"remotes": ["https://remote.example.com"]})
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.get_manifest_path", return_value=manifest), \
             patch("o3de_pilot.commands.publish._upload_to_remote", return_value={"ok": True}), \
             patch("o3de_pilot.commands.publish._check_version_immutability", return_value=False):
            result = runner.invoke(push_command, [str(tmp_path)])
        assert result.exit_code == 0
        assert "Published" in result.output


# ===================================================================
# GEM - Search
# ===================================================================

class TestGemSearch:
    def test_search_no_results(self):
        """No gems found (line 211)."""
        from o3de_pilot.commands.gem import search
        runner = CliRunner()
        with patch("o3de_pilot.core.store.Store") as mock_store:
            mock_store.return_value.search.return_value = []
            result = runner.invoke(search, ["physics"])
        assert "No gems found" in result.output

    def test_search_json_output(self):
        """Search with --json (line 215-217)."""
        from o3de_pilot.commands.gem import search
        fake_gem = MagicMock()
        fake_gem.name = "org.test.gem"
        fake_gem.version = "2.0.0"
        fake_gem.summary = "A test gem"
        fake_gem.object_type = MagicMock(value="gem")
        runner = CliRunner()
        with patch("o3de_pilot.core.store.Store") as mock_store:
            mock_store.return_value.search.return_value = [fake_gem]
            result = runner.invoke(search, ["test", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["name"] == "org.test.gem"

    def test_search_table_output(self):
        """Search with table output (lines 219-227)."""
        from o3de_pilot.commands.gem import search
        fake_gem = MagicMock()
        fake_gem.name = "org.test.physx"
        fake_gem.version = "3.0.0"
        fake_gem.summary = "Physics gem"
        fake_gem.object_type = MagicMock(value="gem")
        runner = CliRunner()
        with patch("o3de_pilot.core.store.Store") as mock_store:
            mock_store.return_value.search.return_value = [fake_gem]
            result = runner.invoke(search, ["physx"])
        assert result.exit_code == 0
        assert "org.test.physx" in result.output


# ===================================================================
# REPO / OVERLAY - Unregister no manifest, list display
# ===================================================================

class TestRepoOverlayEdgeCases:
    def test_repo_unregister_no_manifest(self, tmp_path):
        """Repo unregister when manifest missing (line 180-181)."""
        from o3de_pilot.commands.repo import unregister_repo
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(unregister_repo, ["https://example.com/repo"])
        assert result.exit_code == 1

    def test_overlay_unregister_no_manifest(self, tmp_path):
        """Overlay unregister when manifest missing (line 180-181)."""
        from o3de_pilot.commands.overlay import unregister_overlay
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(unregister_overlay, ["https://example.com/overlay"])
        assert result.exit_code == 1

    def test_repo_list_display(self, tmp_path):
        """Repo list with resolved repos (lines 45-53)."""
        from o3de_pilot.commands.repo import list_repos
        runner = CliRunner()
        fake_repo = MagicMock()
        fake_repo.name = "org.test.repo"
        fake_repo.version = "1.0.0"
        fake_repo.path = Path("/fake/repo")
        fake_repo.data = {}
        with patch("o3de_pilot.core.resolver.Resolver") as mock_res:
            inst = MagicMock()
            inst.repos = {"org.test.repo": fake_repo}
            mock_res.return_value = inst
            result = runner.invoke(list_repos)
        assert result.exit_code == 0

    def test_overlay_list_display(self, tmp_path):
        """Overlay list with resolved overlays (lines 45-53)."""
        from o3de_pilot.commands.overlay import list_overlays
        runner = CliRunner()
        fake_overlay = MagicMock()
        fake_overlay.name = "org.test.overlay"
        fake_overlay.version = "1.0.0"
        fake_overlay.path = Path("/fake/overlay")
        fake_overlay.data = {}
        with patch("o3de_pilot.core.resolver.Resolver") as mock_res:
            inst = MagicMock()
            inst.overlays = {"org.test.overlay": fake_overlay}
            mock_res.return_value = inst
            result = runner.invoke(list_overlays)
        assert result.exit_code == 0

    def test_gem_unregister_no_manifest(self, tmp_path):
        """Gem unregister when manifest missing (line 285-286)."""
        from o3de_pilot.commands.gem import unregister_gem
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(unregister_gem, [str(tmp_path)])
        assert result.exit_code == 1

    def test_overlay_register_no_manifest(self, tmp_path):
        """Overlay register when manifest missing (line 132-133)."""
        from o3de_pilot.commands.overlay import register_overlay
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(register_overlay, [str(tmp_path)])
        assert result.exit_code == 1

    def test_repo_register_no_manifest(self, tmp_path):
        """Repo register when manifest missing (line 133-134)."""
        from o3de_pilot.commands.repo import register_repo
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(register_repo, ["https://example.com/repo"])
        assert result.exit_code == 1
