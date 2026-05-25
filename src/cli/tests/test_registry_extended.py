# O3DE Pilot - Registry Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for registry commands: search, install, refresh, add-remote, etc."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from tests.conftest import _write_json


def _manifest(tmp_path, remotes=None):
    mp = tmp_path / "o3de_manifest.2-0-0.json"
    _write_json(mp, {
        "$schemaVersion": "2.0.0",
        "o3de_manifest": {"name": "test"},
        "local": {"engines": [], "projects": [], "gems": [],
                  "templates": [], "repos": [], "overlays": []},
        "remotes": remotes or [],
    })
    return mp


class TestRegistryAddRemote:
    def test_add_remote(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["add-remote", "https://example.com/repo.json"])
        assert result.exit_code == 0
        assert "Added" in result.output
        data = json.loads(mp.read_text())
        assert "https://example.com/repo.json" in data["remotes"]

    def test_add_remote_duplicate(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path, remotes=["https://example.com/repo.json"])
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["add-remote", "https://example.com/repo.json"])
        assert "Already" in result.output

    def test_add_remote_no_manifest(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = tmp_path / "manifest.json"
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["add-remote", "https://example.com/repo.json"])
        assert result.exit_code == 0
        assert mp.exists()


class TestRegistryRemoveRemote:
    def test_remove_remote(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path, remotes=["https://example.com/repo.json"])
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["remove-remote", "https://example.com/repo.json"])
        assert "Removed" in result.output
        data = json.loads(mp.read_text())
        assert len(data["remotes"]) == 0

    def test_remove_remote_not_found(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["remove-remote", "https://nope.com"])
        assert "Not found" in result.output


class TestRegistryListRemotes:
    def test_list_remotes(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path, remotes=["https://a.com", "https://b.com"])
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["list-remotes"])
        assert "https://a.com" in result.output

    def test_list_remotes_empty(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["list-remotes"])
        assert "No remotes" in result.output

    def test_list_remotes_json(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path, remotes=["https://x.com"])
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["list-remotes", "--json"])
        assert result.exit_code == 0


class TestRegistrySearch:
    def test_search_local(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        resolved = tmp_path / "resolved.json"
        _write_json(resolved, {
            "objects": {
                "org.test.gem.physics": {
                    "name": "org.test.gem.physics",
                    "version": "1.0.0",
                    "type": "gem",
                    "path": "/gems/physics",
                },
            },
        })
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.registry.get_resolved_manifest_path", return_value=resolved), \
             patch("o3de_pilot.commands.registry.Store") as MockStore:
            MockStore.return_value.search.return_value = []
            result = runner.invoke(registry, ["search", "physics"])
        assert "physics" in result.output

    def test_search_no_results(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        resolved = tmp_path / "resolved.json"
        _write_json(resolved, {"objects": {}})
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.registry.get_resolved_manifest_path", return_value=resolved), \
             patch("o3de_pilot.commands.registry.Store") as MockStore:
            MockStore.return_value.search.return_value = []
            result = runner.invoke(registry, ["search", "nonexistent"])
        assert "No results" in result.output

    def test_search_json(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        resolved = tmp_path / "resolved.json"
        _write_json(resolved, {"objects": {}})
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.registry.get_resolved_manifest_path", return_value=resolved), \
             patch("o3de_pilot.commands.registry.Store") as MockStore:
            MockStore.return_value.search.return_value = []
            result = runner.invoke(registry, ["search", "test", "--json"])
        assert result.exit_code == 0


class TestRegistryRefresh:
    def test_refresh_no_manifest(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(registry, ["refresh"])
        assert result.exit_code == 1

    def test_refresh_no_remotes(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["refresh"])
        assert "No remote" in result.output

    def test_refresh_with_remotes(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path, remotes=["https://r1.com"])
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.registry.Store") as MockStore:
            MockStore.return_value.refresh_sync.return_value = None
            result = runner.invoke(registry, ["refresh"])
        assert "Refreshed" in result.output


class TestRegistryUninstall:
    def test_uninstall_removes_from_manifest(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        data = json.loads(mp.read_text())
        data["local"]["gems"] = ["/path/to/org.test.gem.physics"]
        mp.write_text(json.dumps(data))

        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["uninstall", "physics"])
        assert "Removed" in result.output
        data2 = json.loads(mp.read_text())
        assert len(data2["local"]["gems"]) == 0

    def test_uninstall_not_found(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.get_manifest_path", return_value=mp):
            result = runner.invoke(registry, ["uninstall", "nope"])
        assert "not found" in result.output


class TestRegistryUpdate:
    def test_update_all(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.Store") as MockStore:
            MockStore.return_value.refresh_sync.return_value = None
            result = runner.invoke(registry, ["update"])
        assert "Refreshing" in result.output or "updated" in result.output

    def test_update_specific_not_found(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        runner = CliRunner()
        with patch("o3de_pilot.commands.registry.Store") as MockStore:
            MockStore.return_value.search.return_value = []
            result = runner.invoke(registry, ["update", "nonexistent"])
        assert "not found" in result.output
