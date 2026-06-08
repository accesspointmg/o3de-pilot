# O3DE Pilot - Registry & Distribution Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for O2: auth tokens, lockfile, and registry commands."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from tests.conftest import _write_json


# ── Auth Tests ──────────────────────────────────────────────────────

class TestAuth:
    def test_set_and_get_token(self, tmp_path):
        from o3de_pilot.core.auth import set_token, get_token
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "credentials.json"):
            set_token("https://registry.example.com", "my-secret-token")
            assert get_token("https://registry.example.com") == "my-secret-token"

    def test_get_token_nonexistent(self, tmp_path):
        from o3de_pilot.core.auth import get_token
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "credentials.json"):
            assert get_token("https://nonexistent.example.com") is None

    def test_remove_token(self, tmp_path):
        from o3de_pilot.core.auth import set_token, remove_token, get_token
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "credentials.json"):
            set_token("https://registry.example.com", "tok123")
            assert remove_token("https://registry.example.com") is True
            assert get_token("https://registry.example.com") is None

    def test_remove_nonexistent_token(self, tmp_path):
        from o3de_pilot.core.auth import remove_token
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "credentials.json"):
            assert remove_token("https://nope.example.com") is False

    def test_list_registries(self, tmp_path):
        from o3de_pilot.core.auth import set_token, list_registries
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "credentials.json"):
            set_token("https://a.example.com", "tok1")
            set_token("https://b.example.com", "tok2")
            regs = list_registries()
            assert len(regs) == 2

    def test_get_auth_headers(self, tmp_path):
        from o3de_pilot.core.auth import set_token, get_auth_headers
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "credentials.json"):
            set_token("https://r.example.com", "bearer-tok")
            headers = get_auth_headers("https://r.example.com/some/path")
            assert headers["Authorization"] == "Bearer bearer-tok"

    def test_get_auth_headers_no_token(self, tmp_path):
        from o3de_pilot.core.auth import get_auth_headers
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "credentials.json"):
            headers = get_auth_headers("https://noauth.example.com")
            assert headers == {}

    def test_registry_key_normalization(self, tmp_path):
        from o3de_pilot.core.auth import set_token, get_token
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "credentials.json"):
            set_token("https://r.example.com/path/to/repo", "tok")
            # Same origin, different path should match
            assert get_token("https://r.example.com/other/path") == "tok"


# ── Lockfile Tests ──────────────────────────────────────────────────

class TestLockfile:
    def test_generate_lockfile(self, tmp_path):
        from o3de_pilot.core.lockfile import generate_lockfile, LOCKFILE_NAME
        candidates = {
            "org.test.gem.a": {"version": "1.0.0", "type": "gem", "path": "/gems/a"},
            "org.test.gem.b": {"version": "2.0.0", "type": "gem"},
        }
        path = generate_lockfile(tmp_path, candidates, "org.test.engine", "1.0.0")
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["root"] == "org.test.engine"
        assert data["rootVersion"] == "1.0.0"
        assert len(data["packages"]) == 2
        assert data["packages"]["org.test.gem.a"]["version"] == "1.0.0"
        assert data["contentHash"]

    def test_read_lockfile(self, tmp_path):
        from o3de_pilot.core.lockfile import generate_lockfile, read_lockfile
        candidates = {"org.x": {"version": "1.0.0", "type": "gem"}}
        generate_lockfile(tmp_path, candidates, "root", "1.0.0")
        data = read_lockfile(tmp_path)
        assert data is not None
        assert "packages" in data

    def test_read_lockfile_missing(self, tmp_path):
        from o3de_pilot.core.lockfile import read_lockfile
        assert read_lockfile(tmp_path) is None

    def test_verify_lockfile_matches(self, tmp_path):
        from o3de_pilot.core.lockfile import generate_lockfile, verify_lockfile
        candidates = {
            "org.a": {"version": "1.0.0", "type": "gem"},
            "org.b": {"version": "2.0.0", "type": "gem"},
        }
        generate_lockfile(tmp_path, candidates, "root", "1.0.0")
        matches, mismatches = verify_lockfile(tmp_path, candidates)
        assert matches is True
        assert mismatches == []

    def test_verify_lockfile_version_mismatch(self, tmp_path):
        from o3de_pilot.core.lockfile import generate_lockfile, verify_lockfile
        old = {"org.a": {"version": "1.0.0", "type": "gem"}}
        generate_lockfile(tmp_path, old, "root", "1.0.0")
        new = {"org.a": {"version": "2.0.0", "type": "gem"}}
        matches, mismatches = verify_lockfile(tmp_path, new)
        assert matches is False
        assert any("1.0.0" in m and "2.0.0" in m for m in mismatches)

    def test_verify_lockfile_new_package(self, tmp_path):
        from o3de_pilot.core.lockfile import generate_lockfile, verify_lockfile
        old = {"org.a": {"version": "1.0.0", "type": "gem"}}
        generate_lockfile(tmp_path, old, "root", "1.0.0")
        new = {
            "org.a": {"version": "1.0.0", "type": "gem"},
            "org.b": {"version": "1.0.0", "type": "gem"},
        }
        matches, mismatches = verify_lockfile(tmp_path, new)
        assert matches is False
        assert any("org.b" in m for m in mismatches)

    def test_verify_lockfile_removed_package(self, tmp_path):
        from o3de_pilot.core.lockfile import generate_lockfile, verify_lockfile
        old = {
            "org.a": {"version": "1.0.0", "type": "gem"},
            "org.b": {"version": "1.0.0", "type": "gem"},
        }
        generate_lockfile(tmp_path, old, "root", "1.0.0")
        new = {"org.a": {"version": "1.0.0", "type": "gem"}}
        matches, mismatches = verify_lockfile(tmp_path, new)
        assert matches is False

    def test_content_hash_deterministic(self, tmp_path):
        from o3de_pilot.core.lockfile import generate_lockfile, read_lockfile
        candidates = {"org.a": {"version": "1.0.0", "type": "gem"}}
        d1 = tmp_path / "ws1"
        d1.mkdir()
        d2 = tmp_path / "ws2"
        d2.mkdir()
        generate_lockfile(d1, candidates, "root", "1.0.0")
        generate_lockfile(d2, candidates, "root", "1.0.0")
        h1 = read_lockfile(d1)["contentHash"]
        h2 = read_lockfile(d2)["contentHash"]
        assert h1 == h2


# ── Registry CLI Auth Commands ──────────────────────────────────────

class TestRegistryAuthCommands:
    def test_login_with_token(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        runner = CliRunner()
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "creds.json"):
            result = runner.invoke(registry, [
                "login", "https://r.example.com", "--token", "my-token",
            ])
        assert result.exit_code == 0
        assert "saved" in result.output.lower()

    def test_logout(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        runner = CliRunner()
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "creds.json"):
            # Login first
            runner.invoke(registry, ["login", "https://r.example.com", "-t", "tok"])
            # Then logout
            result = runner.invoke(registry, ["logout", "https://r.example.com"])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()

    def test_whoami_authenticated(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        runner = CliRunner()
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "creds.json"):
            runner.invoke(registry, ["login", "https://r.example.com", "-t", "abcd1234efgh"])
            result = runner.invoke(registry, ["whoami", "https://r.example.com"])
        assert result.exit_code == 0
        assert "Authenticated" in result.output

    def test_whoami_not_authenticated(self, tmp_path):
        from o3de_pilot.commands.registry import registry
        runner = CliRunner()
        with patch("o3de_pilot.core.auth.get_credentials_path",
                   return_value=tmp_path / "creds.json"):
            result = runner.invoke(registry, ["whoami", "https://nope.example.com"])
        assert result.exit_code == 0
        assert "Not authenticated" in result.output


# ── Workspace Lock Commands ─────────────────────────────────────────

class TestWorkspaceLock:
    def _make_workspace(self, tmp_path):
        ws = tmp_path / "myws"
        ws.mkdir()
        _write_json(ws / "workspace.json", {
            "$schemaVersion": "2.0.0",
            "name": "myws",
            "version": "1.0.0",
            "root": "org.test.engine",
            "rootVersion": "1.0.0",
            "resolved_candidates": {
                "org.test.gem.a": {"version": "1.0.0", "type": "gem"},
                "org.test.gem.b": {"version": "2.0.0", "type": "gem"},
            },
        })
        return ws

    def test_lock_creates_lockfile(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = self._make_workspace(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path):
            result = runner.invoke(workspace, ["lock", str(ws)])
        assert result.exit_code == 0, f"Lock failed: {result.output}"
        assert (ws / "workspace-lock.json").exists()

    def test_lock_json_output(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = self._make_workspace(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path):
            result = runner.invoke(workspace, ["lock", str(ws), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["packages"] == 2

    def test_verify_lock_passes(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = self._make_workspace(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path):
            runner.invoke(workspace, ["lock", str(ws)])
            result = runner.invoke(workspace, ["verify-lock", str(ws)])
        assert result.exit_code == 0
        assert "verified" in result.output.lower() or "match" in result.output.lower()

    def test_verify_lock_no_lockfile(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = self._make_workspace(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path):
            result = runner.invoke(workspace, ["verify-lock", str(ws)])
        assert result.exit_code == 1

    def test_verify_lock_mismatch(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = self._make_workspace(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path):
            runner.invoke(workspace, ["lock", str(ws)])
        # Modify workspace.json to change a version
        meta = json.loads((ws / "workspace.json").read_text())
        meta["resolved_candidates"]["org.test.gem.a"]["version"] = "9.9.9"
        _write_json(ws / "workspace.json", meta)
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path):
            result = runner.invoke(workspace, ["verify-lock", str(ws)])
        assert result.exit_code == 1
