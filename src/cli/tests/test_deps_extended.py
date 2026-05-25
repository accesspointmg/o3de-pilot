# O3DE Pilot - Deps Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for deps command: tree, list, why."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from tests.conftest import _write_json, make_gem


def _manifest_with_gems(tmp_path, gems_data):
    """Create manifest + gem dirs + resolver-ready structure."""
    gem_paths = []
    for name, version, deps in gems_data:
        gd = make_gem(tmp_path, name, version, deps=deps)
        gem_paths.append(str(gd))

    mp = tmp_path / "o3de_manifest.2-0-0.json"
    _write_json(mp, {
        "$schemaVersion": "2.0.0",
        "o3de_manifest": {"name": "test"},
        "local": {
            "engines": [],
            "projects": [],
            "gems": gem_paths,
            "templates": [],
            "repos": [],
            "overlays": [],
        },
        "remotes": [],
    })
    return mp


class TestTreeCommand:
    def test_tree_full(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.a", "1.0.0", []),
            ("org.test.gem.b", "2.0.0", ["org.test.gem.a"]),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["tree"])
        assert result.exit_code == 0

    def test_tree_named(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.alpha", "1.0.0", []),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["tree", "org.test.gem.alpha"])
        assert result.exit_code == 0
        assert "alpha" in result.output

    def test_tree_missing_name(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.exists", "1.0.0", []),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["tree", "org.nope"])
        assert result.exit_code == 1

    def test_tree_json(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.j", "1.0.0", []),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["tree", "--json"])
        assert result.exit_code == 0

    def test_tree_no_manifest(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(deps, ["tree"])
        assert result.exit_code == 1

    def test_tree_fuzzy_match(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.foobar", "1.0.0", []),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["tree", "foobar_wrong"])
        assert result.exit_code == 1

    def test_tree_all_flag(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.x", "1.0.0", []),
            ("org.test.gem.y", "2.0.0", []),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["tree", "--all"])
        assert result.exit_code == 0


class TestDepsListCommand:
    def test_list_deps_direct(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.base", "1.0.0", []),
            ("org.test.gem.child", "1.0.0", ["org.test.gem.base"]),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["list", "org.test.gem.child"])
        assert result.exit_code == 0
        assert "base" in result.output

    def test_list_deps_no_deps(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.lonely", "1.0.0", []),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["list", "org.test.gem.lonely"])
        assert result.exit_code == 0
        assert "none" in result.output

    def test_list_not_found(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["list", "nope"])
        assert result.exit_code == 1

    def test_list_reverse(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.dep", "1.0.0", []),
            ("org.test.gem.consumer", "1.0.0", ["org.test.gem.dep"]),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["list", "org.test.gem.dep", "--reverse"])
        assert result.exit_code == 0
        assert "consumer" in result.output

    def test_list_transitive(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.root", "1.0.0", []),
            ("org.test.gem.mid", "1.0.0", ["org.test.gem.root"]),
            ("org.test.gem.top", "1.0.0", ["org.test.gem.mid"]),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["list", "org.test.gem.top", "--transitive"])
        assert result.exit_code == 0


class TestWhyCommand:
    def test_why_found(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.leaf", "1.0.0", []),
            ("org.test.gem.mid", "1.0.0", ["org.test.gem.leaf"]),
            ("org.test.gem.root", "1.0.0", ["org.test.gem.mid"]),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["why", "org.test.gem.root", "org.test.gem.leaf"])
        assert result.exit_code == 0
        assert "chain" in result.output.lower() or "->" in result.output

    def test_why_not_found(self, tmp_path):
        from o3de_pilot.commands.deps import deps
        mp = _manifest_with_gems(tmp_path, [
            ("org.test.gem.a1", "1.0.0", []),
            ("org.test.gem.b1", "1.0.0", []),
        ])
        runner = CliRunner()
        with patch("o3de_pilot.commands.deps.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(deps, ["why", "org.test.gem.a1", "org.test.gem.b1"])
        assert result.exit_code == 0
        assert "does not depend" in result.output
