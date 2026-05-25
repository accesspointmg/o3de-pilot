# O3DE Pilot - Manifest Command Extended Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for manifest.py command subcommands."""

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
        "remote": {},
        "remotes": [],
        "country": kw.get("country", {}),
        "default": kw.get("default", {}),
    })
    return mp


def _gem_dir(tmp_path, name="test-gem"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    _write_json(d / "gem.json", {
        "$schemaVersion": "2.0.0",
        "gem": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    return d


# ═══════════════════════════════════════════════════════════════
# manifest show
# ═══════════════════════════════════════════════════════════════

class TestManifestShow:
    def test_show_json(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["show", "--json"])
        assert result.exit_code == 0
        assert "$schemaVersion" in result.output

    def test_show_pretty(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path, gems=["/path/to/gem"])
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["show"])
        assert result.exit_code == 0
        assert "Manifest" in result.output

    def test_show_not_found(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(manifest, ["show"])
        assert result.exit_code != 0

    def test_show_resolved(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        rp = tmp_path / "resolved.json"
        _write_json(rp, {
            "resolved_at": "2024-01-01",
            "objects": {"a": {}, "b": {}},
        })
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_resolved_manifest_path",
                    return_value=rp):
            result = runner.invoke(manifest, ["show", "--resolved"])
        assert result.exit_code == 0
        assert "Resolved" in result.output or "Objects" in result.output


# ═══════════════════════════════════════════════════════════════
# manifest add / remove
# ═══════════════════════════════════════════════════════════════

class TestManifestAdd:
    def test_add_gem(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        d = _gem_dir(tmp_path, "addgem")
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["add", str(d)])
        assert result.exit_code == 0
        assert "Added" in result.output
        data = json.loads(mp.read_text())
        assert len(data["local"]["gems"]) == 1

    def test_add_duplicate(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        d = _gem_dir(tmp_path, "dupgem")
        mp = _manifest(tmp_path, gems=[d.as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["add", str(d)])
        assert "Already" in result.output or "already" in result.output

    def test_add_no_detect(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        empty = tmp_path / "notype"
        empty.mkdir()
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["add", str(empty)])
        assert result.exit_code != 0

    def test_add_with_type(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        d = tmp_path / "myobj"
        d.mkdir()
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["add", str(d), "--type", "gem"])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert len(data["local"]["gems"]) == 1


class TestManifestRemove:
    def test_remove(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        d = _gem_dir(tmp_path, "rmgem")
        mp = _manifest(tmp_path, gems=[d.as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["remove", str(d)])
        assert "Removed" in result.output
        data = json.loads(mp.read_text())
        assert len(data["local"]["gems"]) == 0

    def test_remove_not_found(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["remove", str(tmp_path / "nope")])
        assert "Not found" in result.output or "not found" in result.output

    def test_remove_no_manifest(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(manifest, ["remove", "/some/path"])
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════
# manifest set / get
# ═══════════════════════════════════════════════════════════════

class TestManifestSet:
    def test_set_country(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["set", "country.code", "CA"])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert data["country"]["code"] == "CA"

    def test_set_default_path(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["set", "default.gems_path", "C:\\O3DE\\Gems"])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert "/" in data["default"]["gems_path"]  # normalized to posix

    def test_set_invalid_key(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["set", "bad", "val"])
        assert result.exit_code != 0

    def test_set_unknown_section(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["set", "unknown.field", "val"])
        assert result.exit_code != 0

    def test_set_update_existing(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path, country={"code": "US"})
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["set", "country.code", "GB"])
        assert "Updated" in result.output
        data = json.loads(mp.read_text())
        assert data["country"]["code"] == "GB"


class TestManifestGet:
    def test_get_all(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path, country={"code": "CA"}, default={"gems_path": "/g"})
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["get"])
        assert result.exit_code == 0
        assert "CA" in result.output

    def test_get_specific(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path, country={"code": "US"})
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["get", "country.code"])
        assert "US" in result.output

    def test_get_not_set(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["get", "country.code"])
        assert "Not set" in result.output

    def test_get_invalid_key(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=mp):
            result = runner.invoke(manifest, ["get", "bad"])
        assert result.exit_code != 0

    def test_get_no_manifest(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        runner = CliRunner()
        with patch("o3de_pilot.commands.manifest.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(manifest, ["get"])
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════
# manifest upgrade
# ═══════════════════════════════════════════════════════════════

class TestManifestUpgrade:
    def test_upgrade_file_already_latest(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        gf = tmp_path / "gem.json"
        _write_json(gf, {"$schemaVersion": "2.0.0", "gem": {"name": "x"}})
        runner = CliRunner()
        result = runner.invoke(manifest, ["upgrade", str(gf)])
        assert result.exit_code == 0
        assert "Already" in result.output or "latest" in result.output

    def test_upgrade_not_found(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        runner = CliRunner()
        # Click validates exists=True so pass a nonexistent path
        result = runner.invoke(manifest, ["upgrade", str(tmp_path / "nope")])
        assert result.exit_code != 0

    def test_upgrade_dir_dry_run(self, tmp_path):
        from o3de_pilot.commands.manifest import manifest
        _write_json(tmp_path / "gem.json", {"gem": {"name": "x"}})
        runner = CliRunner()
        result = runner.invoke(manifest, ["upgrade", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
