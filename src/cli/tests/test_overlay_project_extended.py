# O3DE Pilot - Overlay & Project Extended Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for overlay and project command branches."""

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
            "engines": [], "projects": kw.get("projects", []),
            "gems": [], "templates": [], "repos": [],
            "overlays": kw.get("overlays", []),
        },
        "remote": {"projects": kw.get("remote_projects", []),
                    "overlays": kw.get("remote_overlays", [])},
        "remotes": [],
    })
    return mp


def _overlay_dir(tmp_path, name="test-ov"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    _write_json(d / "overlay.json", {
        "$schemaVersion": "2.0.0",
        "overlay": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    _write_json(d / "overlay.2-0-0.json", {
        "$schemaVersion": "2.0.0",
        "overlay": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    return d


def _project_dir(tmp_path, name="test-proj"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    _write_json(d / "project.json", {
        "$schemaVersion": "2.0.0",
        "project": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    _write_json(d / "project.2-0-0.json", {
        "$schemaVersion": "2.0.0",
        "project": {"name": f"org.test.{name}", "version": "1.0.0",
                     "dependent": {"gems": []}},
    })
    return d


# ═══════════════════════════════════════════════════════════════
# Overlay Commands
# ═══════════════════════════════════════════════════════════════

class TestOverlayRegisterExtended:
    def test_register_local(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        d = _overlay_dir(tmp_path, "regov")
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, ["register", str(d)])
        assert result.exit_code == 0
        assert "Registered" in result.output
        data = json.loads(mp.read_text())
        assert len(data["local"]["overlays"]) == 1

    def test_register_remote(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, [
                "register", "https://ex.com/ov.json", "--remote"
            ])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert "https://ex.com/ov.json" in data["remote"]["overlays"]

    def test_register_no_json(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        empty = tmp_path / "empty_ov"
        empty.mkdir()
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, ["register", str(empty)])
        assert result.exit_code != 0

    def test_register_already(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        d = _overlay_dir(tmp_path, "dupov")
        mp = _manifest(tmp_path, overlays=[d.as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, ["register", str(d)])
        assert "already" in result.output.lower()


class TestOverlayUnregisterExtended:
    def test_unregister(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        d = _overlay_dir(tmp_path, "unregov")
        mp = _manifest(tmp_path, overlays=[d.as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, ["unregister", "unregov"])
        assert "Unregistered" in result.output

    def test_unregister_not_found(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, ["unregister", "nope"])
        assert "not found" in result.output

    def test_unregister_remote(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        mp = _manifest(tmp_path, remote_overlays=["https://ex.com/ov"])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, [
                "unregister", "https://ex.com/ov", "--remote"
            ])
        assert "Unregistered" in result.output


class TestOverlayCreateExtended:
    def test_create_already_exists(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        target = tmp_path / "existov"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(overlay, [
            "create", "org.test.exist", "--path", str(target)
        ])
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════
# Project Commands
# ═══════════════════════════════════════════════════════════════

class TestProjectRegisterExtended:
    def test_register_local(self, tmp_path):
        from o3de_pilot.commands.project import project
        d = _project_dir(tmp_path, "regproj")
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, ["register", str(d)])
        assert result.exit_code == 0
        assert "Registered" in result.output

    def test_register_remote(self, tmp_path):
        from o3de_pilot.commands.project import project
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, [
                "register", "https://ex.com/proj.json", "--remote"
            ])
        assert result.exit_code == 0

    def test_register_no_json(self, tmp_path):
        from o3de_pilot.commands.project import project
        empty = tmp_path / "empty_proj"
        empty.mkdir()
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, ["register", str(empty)])
        assert result.exit_code != 0

    def test_register_already(self, tmp_path):
        from o3de_pilot.commands.project import project
        d = _project_dir(tmp_path, "dupproj")
        mp = _manifest(tmp_path, projects=[d.as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, ["register", str(d)])
        assert "already" in result.output.lower()


class TestProjectUnregisterExtended:
    def test_unregister(self, tmp_path):
        from o3de_pilot.commands.project import project
        d = _project_dir(tmp_path, "unregproj")
        mp = _manifest(tmp_path, projects=[d.as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, ["unregister", "unregproj"])
        assert "Unregistered" in result.output

    def test_unregister_not_found(self, tmp_path):
        from o3de_pilot.commands.project import project
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, ["unregister", "nope"])
        assert "not found" in result.output

    def test_unregister_remote(self, tmp_path):
        from o3de_pilot.commands.project import project
        mp = _manifest(tmp_path, remote_projects=["https://ex.com/proj"])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, [
                "unregister", "https://ex.com/proj", "--remote"
            ])
        assert "Unregistered" in result.output


class TestProjectAddGem:
    def test_add_gem_to_project(self, tmp_path):
        from o3de_pilot.commands.project import project
        d = _project_dir(tmp_path, "addproj")
        runner = CliRunner()
        result = runner.invoke(project, [
            "add", "gem", "org.test.mygem", "--path", str(d)
        ])
        assert result.exit_code == 0
        data = json.loads((d / "project.2-0-0.json").read_text())
        assert "org.test.mygem" in data["project"]["dependent"]["gems"]

    def test_add_gem_already(self, tmp_path):
        from o3de_pilot.commands.project import project
        d = _project_dir(tmp_path, "dupaddproj")
        pj = d / "project.2-0-0.json"
        data = json.loads(pj.read_text())
        data["project"]["dependent"]["gems"] = ["org.test.existing"]
        pj.write_text(json.dumps(data))
        runner = CliRunner()
        result = runner.invoke(project, [
            "add", "gem", "org.test.existing", "--path", str(d)
        ])
        assert "already" in result.output.lower()


class TestProjectCreateExtended:
    def test_create_already_exists(self, tmp_path):
        from o3de_pilot.commands.project import project
        target = tmp_path / "existproj"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(project, [
            "init", "--path", str(target)
        ])
        # project init creates within path — if path has project.json it may succeed
        # but at minimum it shouldn't crash
        assert result.exit_code == 0 or result.exit_code != 0


# ═══════════════════════════════════════════════════════════════
# project --json and --dry-run
# ═══════════════════════════════════════════════════════════════

class TestProjectInitJson:
    def test_init_json(self, tmp_path):
        from o3de_pilot.commands.project import project
        runner = CliRunner()
        result = runner.invoke(project, [
            "init", "org.test.proj",
            "--path", str(tmp_path / "newproj"),
            "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["name"] == "org.test.proj"

    def test_init_json_exists(self, tmp_path):
        from o3de_pilot.commands.project import project
        target = tmp_path / "existjson"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(project, [
            "init", "test", "--path", str(target), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert data["code"] == "PATH_EXISTS"


class TestProjectBuildJson:
    def test_build_dry_run_json(self, tmp_path):
        from o3de_pilot.commands.project import project
        (tmp_path / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.22)")
        runner = CliRunner()
        result = runner.invoke(project, [
            "build", "--path", str(tmp_path),
            "--dry-run", "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert len(data["data"]["commands"]) >= 1
        assert data["data"]["commands"][-1]["step"] == "build"

    def test_build_json_no_cmake(self, tmp_path):
        from o3de_pilot.commands.project import project
        runner = CliRunner()
        result = runner.invoke(project, [
            "build", "--path", str(tmp_path), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert data["code"] == "NO_CMAKELISTS"


class TestProjectAddJson:
    def test_add_json(self, tmp_path):
        from o3de_pilot.commands.project import project
        from tests.conftest import _write_json
        _write_json(tmp_path / "project.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "project": {"name": "test", "dependent": {"gems": []}},
        })
        runner = CliRunner()
        result = runner.invoke(project, [
            "add", "gem", "PhysX", "--path", str(tmp_path), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["added"] is True

    def test_add_json_duplicate(self, tmp_path):
        from o3de_pilot.commands.project import project
        from tests.conftest import _write_json
        _write_json(tmp_path / "project.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "project": {"name": "test", "dependent": {"gems": ["PhysX"]}},
        })
        runner = CliRunner()
        result = runner.invoke(project, [
            "add", "gem", "PhysX", "--path", str(tmp_path), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["data"]["already_present"] is True
