# O3DE Pilot - Gem & Workspace Command Extended Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for gem and workspace command subcommands."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from tests.conftest import _write_json


def _manifest(tmp_path, **kw):
    mp = tmp_path / "o3de_manifest.2-0-0.json"
    _write_json(mp, {
        "$schemaVersion": "2.0.0",
        "o3de_manifest": {"name": "test"},
        "local": {
            "engines": [], "projects": [],
            "gems": kw.get("gems", []),
            "templates": [], "repos": [], "overlays": [],
        },
        "remote": {"gems": kw.get("remote_gems", [])},
        "remotes": [],
    })
    return mp


def _gem_dir(tmp_path, name="test-gem"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    _write_json(d / "gem.json", {
        "$schemaVersion": "2.0.0",
        "gem": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    _write_json(d / "gem.2-0-0.json", {
        "$schemaVersion": "2.0.0",
        "gem": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    return d


# ═══════════════════════════════════════════════════════════════
# Gem Commands
# ═══════════════════════════════════════════════════════════════

class TestGemInfo:
    def test_info_found(self):
        from o3de_pilot.commands.gem import gem
        resolved_data = {
            "objects": {
                "org.test.mygem": {
                    "name": "org.test.mygem",
                    "version": "1.0.0",
                    "type": "gem",
                    "path": "/some/path",
                },
            },
        }
        runner = CliRunner()
        with patch("o3de_pilot.core.resolver.load_resolved_manifest",
                    return_value=resolved_data):
            result = runner.invoke(gem, ["info", "org.test.mygem"])
        assert result.exit_code == 0
        assert "mygem" in result.output

    def test_info_not_found(self):
        from o3de_pilot.commands.gem import gem
        runner = CliRunner()
        with patch("o3de_pilot.core.resolver.load_resolved_manifest",
                    return_value={"objects": {}}):
            result = runner.invoke(gem, ["info", "nope"])
        assert result.exit_code != 0


class TestGemRegister:
    def test_register_local(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        d = _gem_dir(tmp_path, "reggem")
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(gem, ["register", str(d)])
        assert result.exit_code == 0
        assert "Registered" in result.output
        data = json.loads(mp.read_text())
        assert len(data["local"]["gems"]) == 1

    def test_register_remote(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(gem, [
                "register", "https://ex.com/gem.json", "--remote"
            ])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert "https://ex.com/gem.json" in data["remote"]["gems"]

    def test_register_no_json(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        empty = tmp_path / "empty_gem"
        empty.mkdir()
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(gem, ["register", str(empty)])
        assert result.exit_code != 0

    def test_register_already(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        d = _gem_dir(tmp_path, "dupgem")
        mp = _manifest(tmp_path, gems=[d.as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(gem, ["register", str(d)])
        assert "already" in result.output.lower()


class TestGemUnregister:
    def test_unregister_local(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        d = _gem_dir(tmp_path, "unreggem")
        mp = _manifest(tmp_path, gems=[d.as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(gem, ["unregister", "unreggem"])
        assert "Unregistered" in result.output

    def test_unregister_not_found(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(gem, ["unregister", "nope"])
        assert "not found" in result.output

    def test_unregister_remote(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        mp = _manifest(tmp_path, remote_gems=["https://ex.com/gem.json"])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(gem, ["unregister", "https://ex.com/gem.json", "--remote"])
        assert "Unregistered" in result.output


class TestGemCreateExtended:
    def test_create_already_exists(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        target = tmp_path / "existgem"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(gem, [
            "create", "org.test.exist", "--path", str(target)
        ])
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════
# Workspace Commands
# ═══════════════════════════════════════════════════════════════

class TestWorkspaceList:
    def test_list_empty(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path / "noexist"), \
             patch("o3de_pilot.commands.workspace._get_registered_workspaces",
                    return_value=[]):
            result = runner.invoke(workspace, ["list"])
        assert result.exit_code == 0
        assert "No workspaces" in result.output

    def test_list_json_empty(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path / "noexist"), \
             patch("o3de_pilot.commands.workspace._get_registered_workspaces",
                    return_value=[]):
            result = runner.invoke(workspace, ["list", "--json"])
        assert result.exit_code == 0
        assert "[]" in result.output

    def test_list_with_workspace(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws_dir = tmp_path / "ws1"
        ws_dir.mkdir()
        _write_json(ws_dir / ".workspace.json", {
            "name": "ws1",
            "created": "2024-01-01",
            "sources": [],
            "overlays": [],
        })
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path), \
             patch("o3de_pilot.commands.workspace._get_registered_workspaces",
                    return_value=[]):
            result = runner.invoke(workspace, ["list"])
        assert "ws1" in result.output


class TestWorkspaceShow:
    def test_show(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws_dir = tmp_path / "showws"
        ws_dir.mkdir()
        _write_json(ws_dir / ".workspace.json", {
            "name": "showws",
            "created": "2024-01-01",
            "sources": ["/src1"],
            "overlays": ["/ov1"],
        })
        runner = CliRunner()
        result = runner.invoke(workspace, ["show", str(ws_dir)])
        assert result.exit_code == 0
        assert "showws" in result.output

    def test_show_json(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws_dir = tmp_path / "showws2"
        ws_dir.mkdir()
        _write_json(ws_dir / ".workspace.json", {
            "name": "showws2",
            "created": "2024-01-01",
            "sources": [],
            "overlays": [],
        })
        runner = CliRunner()
        result = runner.invoke(workspace, ["show", str(ws_dir), "--json"])
        assert result.exit_code == 0

    def test_show_not_found(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path):
            result = runner.invoke(workspace, ["show", "nope"])
        assert result.exit_code != 0

    def test_show_no_meta(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws_dir = tmp_path / "nometa"
        ws_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(workspace, ["show", str(ws_dir)])
        assert result.exit_code != 0


class TestWorkspaceDelete:
    def test_delete_force(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws_dir = tmp_path / "delws"
        ws_dir.mkdir()
        (ws_dir / "file.txt").write_text("x")
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace._unregister_workspace"):
            result = runner.invoke(workspace, ["delete", str(ws_dir), "--force"])
        assert result.exit_code == 0
        assert not ws_dir.exists()

    def test_delete_not_found(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path):
            result = runner.invoke(workspace, ["delete", "nope"])
        assert result.exit_code != 0


class TestWorkspaceTree:
    def test_tree(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws_dir = tmp_path / "treews"
        ws_dir.mkdir()
        (ws_dir / "sub").mkdir()
        (ws_dir / "sub" / "a.txt").write_text("a")
        runner = CliRunner()
        result = runner.invoke(workspace, ["tree", str(ws_dir)])
        assert result.exit_code == 0

    def test_tree_not_found(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path):
            result = runner.invoke(workspace, ["tree", "nope"])
        assert result.exit_code != 0


class TestWorkspaceUpdate:
    def test_update_not_found(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path):
            result = runner.invoke(workspace, ["update", "nope"])
        assert result.exit_code != 0

    def test_update_no_meta(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws_dir = tmp_path / "nometa"
        ws_dir.mkdir()
        runner = CliRunner()
        result = runner.invoke(workspace, ["update", str(ws_dir)])
        assert result.exit_code != 0
