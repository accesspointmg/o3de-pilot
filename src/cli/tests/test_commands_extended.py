# O3DE Pilot - Extended Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Extended tests for CLI command modules — covers create, register, unregister, list, audit."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from tests.conftest import _write_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_manifest(tmp_path, **kw):
    """Create manifest with object paths pre-registered."""
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


def _make_obj(tmp_path, obj_type, name, version="1.0.0"):
    """Create a minimal object dir with JSON."""
    d = tmp_path / name.replace(".", "_")
    d.mkdir(parents=True, exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        obj_type: {"name": name, "version": version, "display_name": name},
    }
    _write_json(d / f"{obj_type}.json", data)
    # Also create versioned file for register detection
    _write_json(d / f"{obj_type}.2-0-0.json", data)
    return d


# ===================================================================
# Engine Commands
# ===================================================================

class TestEngineList:
    def test_list_json(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        eng = _make_obj(tmp_path, "engine", "org.test.eng")
        mp = _setup_manifest(tmp_path, engines=[str(eng)])

        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(engine, ["list", "--json"])

        assert result.exit_code == 0
        items = json.loads(result.output)
        assert any(e["name"] == "org.test.eng" for e in items)

    def test_list_table(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        eng = _make_obj(tmp_path, "engine", "org.test.eng2")
        mp = _setup_manifest(tmp_path, engines=[str(eng)])

        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(engine, ["list"])

        assert result.exit_code == 0
        assert "org.test.eng2" in result.output

    def test_list_empty(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        mp = _setup_manifest(tmp_path)

        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(engine, ["list"])

        assert result.exit_code == 0
        assert "No engines" in result.output


class TestEngineCreate:
    def test_create_engine(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        runner = CliRunner()
        target = tmp_path / "new_eng"

        result = runner.invoke(engine, ["create", "org.test.eng.new", "--path", str(target)])

        assert result.exit_code == 0
        assert target.exists()
        assert (target / "engine.2-0-0.json").exists()
        data = json.loads((target / "engine.2-0-0.json").read_text())
        assert data["engine"]["name"] == "org.test.eng.new"

    def test_create_existing_fails(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        target = tmp_path / "exists"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(engine, ["create", "test", "--path", str(target)])
        assert result.exit_code != 0


class TestEngineRegister:
    def test_register_local(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        eng = _make_obj(tmp_path, "engine", "org.reg.eng")
        mp = _setup_manifest(tmp_path)

        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(engine, ["register", str(eng)])

        assert result.exit_code == 0
        assert "Registered" in result.output
        data = json.loads(mp.read_text())
        assert any(str(eng.resolve().as_posix()) in p for p in data["local"]["engines"])

    def test_register_remote(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(engine, ["register", "https://example.com/engine.json", "--remote"])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert "https://example.com/engine.json" in data["remote"]["engines"]

    def test_register_duplicate(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        eng = _make_obj(tmp_path, "engine", "org.dup.eng")
        mp = _setup_manifest(tmp_path, engines=[eng.resolve().as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(engine, ["register", str(eng)])
        assert "already registered" in result.output

    def test_register_no_json_fails(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        empty = tmp_path / "empty"
        empty.mkdir()
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(engine, ["register", str(empty)])
        assert result.exit_code != 0


class TestEngineUnregister:
    def test_unregister(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        mp = _setup_manifest(tmp_path, engines=["/path/to/org.test.eng"])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(engine, ["unregister", "org.test.eng"])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert len(data["local"]["engines"]) == 0

    def test_unregister_not_found(self, tmp_path):
        from o3de_pilot.commands.engine import engine
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(engine, ["unregister", "nope"])
        assert "not found" in result.output


# ===================================================================
# Project Commands
# ===================================================================

class TestProjectList:
    def test_list_json(self, tmp_path):
        from o3de_pilot.commands.project import project
        proj = _make_obj(tmp_path, "project", "org.test.proj")
        mp = _setup_manifest(tmp_path, projects=[str(proj)])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(project, ["list", "--json"])
        assert result.exit_code == 0
        items = json.loads(result.output)
        assert any(p["name"] == "org.test.proj" for p in items)

    def test_list_empty(self, tmp_path):
        from o3de_pilot.commands.project import project
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(project, ["list"])
        assert "No projects" in result.output


class TestProjectInit:
    def test_init_creates_structure(self, tmp_path):
        from o3de_pilot.commands.project import project
        runner = CliRunner()
        target = tmp_path / "myproj"
        result = runner.invoke(project, ["init", "org.test.proj", "--path", str(target)])
        assert result.exit_code == 0
        assert (target / "project.2-0-0.json").exists()
        assert (target / "Code").is_dir()
        assert (target / "Gems").is_dir()
        assert (target / "CMakeLists.txt").exists()


class TestProjectRegister:
    def test_register_local(self, tmp_path):
        from o3de_pilot.commands.project import project
        proj = _make_obj(tmp_path, "project", "org.reg.proj")
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, ["register", str(proj)])
        assert result.exit_code == 0
        assert "Registered" in result.output

    def test_register_no_json_fails(self, tmp_path):
        from o3de_pilot.commands.project import project
        empty = tmp_path / "noproj"
        empty.mkdir()
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, ["register", str(empty)])
        assert result.exit_code != 0


class TestProjectUnregister:
    def test_unregister(self, tmp_path):
        from o3de_pilot.commands.project import project
        mp = _setup_manifest(tmp_path, projects=["/path/to/org.test.proj"])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(project, ["unregister", "org.test.proj"])
        assert result.exit_code == 0


class TestProjectAdd:
    def test_add_gem(self, tmp_path):
        from o3de_pilot.commands.project import project
        proj = _make_obj(tmp_path, "project", "myproj")
        runner = CliRunner()
        result = runner.invoke(project, ["add", "gem", "org.test.gem.physics", "--path", str(proj)])
        assert result.exit_code == 0
        data = json.loads((proj / "project.2-0-0.json").read_text())
        assert "org.test.gem.physics" in data["project"]["dependent"]["gems"]


# ===================================================================
# Gem Commands
# ===================================================================

class TestGemList:
    def test_list_json(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        g = _make_obj(tmp_path, "gem", "org.test.gem.a")
        mp = _setup_manifest(tmp_path, gems=[str(g)])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(gem, ["list", "--json"])
        assert result.exit_code == 0
        items = json.loads(result.output)
        assert any(g["name"] == "org.test.gem.a" for g in items)

    def test_list_empty(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(gem, ["list"])
        assert "No gems" in result.output


class TestGemCreate:
    def test_create_gem(self, tmp_path):
        from o3de_pilot.commands.gem import gem
        target = tmp_path / "newgem"
        runner = CliRunner()
        result = runner.invoke(gem, ["create", "org.test.gem.new", "--path", str(target)])
        assert result.exit_code == 0
        assert (target / "gem.2-0-0.json").exists()
        assert (target / "Code" / "Source").is_dir()


# ===================================================================
# Template Commands
# ===================================================================

class TestTemplateList:
    def test_list_json(self, tmp_path):
        from o3de_pilot.commands.template import template
        tpl = _make_obj(tmp_path, "template", "org.test.tpl")
        mp = _setup_manifest(tmp_path, templates=[str(tpl)])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(template, ["list", "--json"])
        assert result.exit_code == 0
        items = json.loads(result.output)
        assert any(t["name"] == "org.test.tpl" for t in items)

    def test_list_empty(self, tmp_path):
        from o3de_pilot.commands.template import template
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(template, ["list"])
        assert "No templates" in result.output


class TestTemplateCreate:
    def test_create_template(self, tmp_path):
        from o3de_pilot.commands.template import template
        target = tmp_path / "newtpl"
        runner = CliRunner()
        result = runner.invoke(template, ["create", "org.test.tpl.new", "--path", str(target)])
        assert result.exit_code == 0
        assert target.exists()
        # Check for template JSON
        jsons = list(target.glob("template*.json"))
        assert len(jsons) >= 1


# ===================================================================
# Overlay Commands
# ===================================================================

class TestOverlayList:
    def test_list_json(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        ov = _make_obj(tmp_path, "overlay", "org.test.ov")
        mp = _setup_manifest(tmp_path, overlays=[str(ov)])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(overlay, ["list", "--json"])
        assert result.exit_code == 0
        items = json.loads(result.output)
        assert any(o["name"] == "org.test.ov" for o in items)

    def test_list_empty(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(overlay, ["list"])
        assert "No overlays" in result.output


class TestOverlayCreate:
    def test_create_overlay(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        target = tmp_path / "newov"
        runner = CliRunner()
        result = runner.invoke(overlay, ["create", "org.test.ov.new", "--path", str(target)])
        assert result.exit_code == 0
        assert (target / "overlay.2-0-0.json").exists()


class TestOverlayRegister:
    def test_register_local(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        ov = _make_obj(tmp_path, "overlay", "org.reg.ov")
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, ["register", str(ov)])
        assert result.exit_code == 0
        assert "Registered" in result.output

    def test_register_no_json_fails(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        empty = tmp_path / "empty_ov"
        empty.mkdir()
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, ["register", str(empty)])
        assert result.exit_code != 0


class TestOverlayUnregister:
    def test_unregister(self, tmp_path):
        from o3de_pilot.commands.overlay import overlay
        mp = _setup_manifest(tmp_path, overlays=["/path/to/org.test.ov"])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(overlay, ["unregister", "org.test.ov"])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert len(data["local"]["overlays"]) == 0


# ===================================================================
# Repo Commands
# ===================================================================

class TestRepoList:
    def test_list_empty(self, tmp_path):
        from o3de_pilot.commands.repo import repo
        mp = _setup_manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(repo, ["list"])
        assert "No repos" in result.output


class TestRepoCreate:
    def test_create_repo(self, tmp_path):
        from o3de_pilot.commands.repo import repo
        target = tmp_path / "newrepo"
        runner = CliRunner()
        result = runner.invoke(repo, ["create", "org.test.repo.new", "--path", str(target)])
        assert result.exit_code == 0
        assert (target / "repo.2-0-0.json").exists()


# ===================================================================
# Audit Commands
# ===================================================================

class TestAuditCommand:
    def test_audit_clean(self, tmp_path):
        from o3de_pilot.commands.audit import audit
        gem = _make_obj(tmp_path, "gem", "org.clean.gem")
        mp = _setup_manifest(tmp_path, gems=[str(gem)])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.audit.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(audit)
        assert result.exit_code == 0
        assert "healthy" in result.output or "No issues" in result.output

    def test_audit_json_clean(self, tmp_path):
        from o3de_pilot.commands.audit import audit
        gem = _make_obj(tmp_path, "gem", "org.clean2.gem")
        mp = _setup_manifest(tmp_path, gems=[str(gem)])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.audit.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(audit, ["--json"])
        assert result.exit_code == 0

    def test_audit_detects_missing_dep(self, tmp_path):
        from o3de_pilot.commands.audit import audit
        gem_dir = tmp_path / "depgem"
        gem_dir.mkdir()
        _write_json(gem_dir / "gem.json", {
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.dep.gem",
                "version": "1.0.0",
                "dependent": {"gems": ["org.missing.gem"]},
            },
        })
        mp = _setup_manifest(tmp_path, gems=[str(gem_dir)])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.audit.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(audit)
        # Should exit 1 because there are issues
        assert result.exit_code == 1

    def test_audit_no_manifest(self, tmp_path):
        from o3de_pilot.commands.audit import audit
        runner = CliRunner()
        with patch("o3de_pilot.commands.audit.get_manifest_path",
                    return_value=tmp_path / "nonexistent.json"):
            result = runner.invoke(audit)
        assert result.exit_code != 0
