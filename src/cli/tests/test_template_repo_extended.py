# O3DE Pilot - Template & Repo Extended Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Additional tests for template and repo command branches."""

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
            "engines": [], "projects": [], "gems": [],
            "templates": kw.get("templates", []),
            "repos": kw.get("repos", []),
            "overlays": [],
        },
        "remote": {"templates": [], "repos": []},
        "remotes": [],
    })
    return mp


def _tpl_dir(tmp_path, name="test-tpl"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    _write_json(d / "template.json", {
        "$schemaVersion": "2.0.0",
        "template": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    _write_json(d / "template.2-0-0.json", {
        "$schemaVersion": "2.0.0",
        "template": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    return d


def _repo_dir(tmp_path, name="test-repo"):
    d = tmp_path / name
    d.mkdir(exist_ok=True)
    _write_json(d / "repo.json", {
        "$schemaVersion": "2.0.0",
        "repo": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    _write_json(d / "repo.2-0-0.json", {
        "$schemaVersion": "2.0.0",
        "repo": {"name": f"org.test.{name}", "version": "1.0.0"},
    })
    return d


# ═══════════════════════════════════════════════════════════════
# Template Commands
# ═══════════════════════════════════════════════════════════════

class TestTemplateInfo:
    def test_info_found(self, tmp_path):
        from o3de_pilot.commands.template import template
        tpl = _tpl_dir(tmp_path, "infotpl")
        resolved_data = {
            "objects": {
                "org.test.infotpl": {
                    "name": "org.test.infotpl",
                    "version": "1.0.0",
                    "type": "template",
                    "path": str(tpl),
                },
            },
        }
        runner = CliRunner()
        with patch("o3de_pilot.core.resolver.load_resolved_manifest", return_value=resolved_data):
            result = runner.invoke(template, ["info", "org.test.infotpl"])
        assert result.exit_code == 0
        assert "infotpl" in result.output

    def test_info_not_found(self, tmp_path):
        from o3de_pilot.commands.template import template
        runner = CliRunner()
        with patch("o3de_pilot.core.resolver.load_resolved_manifest", return_value={"objects": {}}):
            result = runner.invoke(template, ["info", "nope"])
        assert result.exit_code != 0


class TestTemplateCreateExtended:
    def test_create_from_source(self, tmp_path):
        from o3de_pilot.commands.template import template
        src = tmp_path / "source"
        src.mkdir()
        (src / "readme.txt").write_text("hello")
        target = tmp_path / "newtpl"
        runner = CliRunner()
        result = runner.invoke(template, [
            "create", "org.test.tpl.new",
            "--path", str(target),
            "--source", str(src),
        ])
        assert result.exit_code == 0
        assert (target / "readme.txt").exists()
        assert (target / "template.2-0-0.json").exists()

    def test_create_existing_fails(self, tmp_path):
        from o3de_pilot.commands.template import template
        target = tmp_path / "exists"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(template, ["create", "test", "--path", str(target)])
        assert result.exit_code != 0


class TestTemplateRegister:
    def test_register_local(self, tmp_path):
        from o3de_pilot.commands.template import template
        d = _tpl_dir(tmp_path, "regtpl")
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(template, ["register", str(d)])
        assert result.exit_code == 0
        assert "Registered" in result.output

    def test_register_remote(self, tmp_path):
        from o3de_pilot.commands.template import template
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(template, ["register", "https://ex.com/tpl.json", "--remote"])
        assert result.exit_code == 0

    def test_register_no_json(self, tmp_path):
        from o3de_pilot.commands.template import template
        empty = tmp_path / "empty_tpl"
        empty.mkdir()
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(template, ["register", str(empty)])
        assert result.exit_code != 0


class TestTemplateUnregister:
    def test_unregister(self, tmp_path):
        from o3de_pilot.commands.template import template
        mp = _manifest(tmp_path, templates=["/path/to/org.test.tpl"])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(template, ["unregister", "org.test.tpl"])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert len(data["local"]["templates"]) == 0

    def test_unregister_not_found(self, tmp_path):
        from o3de_pilot.commands.template import template
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(template, ["unregister", "nope"])
        assert "not found" in result.output


# ═══════════════════════════════════════════════════════════════
# Repo Commands
# ═══════════════════════════════════════════════════════════════

class TestRepoList:
    def test_list_json(self, tmp_path):
        from o3de_pilot.commands.repo import repo
        d = _repo_dir(tmp_path, "listrepo")
        mp = _manifest(tmp_path, repos=[str(d)])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(repo, ["list", "--json"])
        assert result.exit_code == 0


class TestRepoRegister:
    def test_register_local(self, tmp_path):
        from o3de_pilot.commands.repo import repo
        d = _repo_dir(tmp_path, "regrepo")
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(repo, ["register", str(d)])
        assert result.exit_code == 0
        assert "Registered" in result.output

    def test_register_remote(self, tmp_path):
        from o3de_pilot.commands.repo import repo
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(repo, ["register", "https://ex.com/repo.json", "--remote"])
        assert result.exit_code == 0

    def test_register_no_json(self, tmp_path):
        from o3de_pilot.commands.repo import repo
        empty = tmp_path / "empty_repo"
        empty.mkdir()
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(repo, ["register", str(empty)])
        assert result.exit_code != 0


class TestRepoUnregister:
    def test_unregister(self, tmp_path):
        from o3de_pilot.commands.repo import repo
        mp = _manifest(tmp_path, repos=["/path/to/org.test.repo"])
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(repo, ["unregister", "org.test.repo"])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert len(data["local"]["repos"]) == 0

    def test_unregister_not_found(self, tmp_path):
        from o3de_pilot.commands.repo import repo
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.core.paths.get_manifest_path", return_value=mp):
            result = runner.invoke(repo, ["unregister", "nope"])
        assert "not found" in result.output


# ═══════════════════════════════════════════════════════════════
# template --json and --dry-run tests
# ═══════════════════════════════════════════════════════════════

class TestTemplateInfoJson:
    def test_info_json(self):
        from o3de_pilot.commands.template import template
        runner = CliRunner()
        resolved = {
            "objects": {
                "org.test.tpl": {"type": "template", "version": "1.0.0", "path": "/t"}
            }
        }
        with patch("o3de_pilot.core.resolver.load_resolved_manifest", return_value=resolved):
            result = runner.invoke(template, ["info", "org.test.tpl", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["version"] == "1.0.0"

    def test_info_json_not_found(self):
        from o3de_pilot.commands.template import template
        runner = CliRunner()
        with patch("o3de_pilot.core.resolver.load_resolved_manifest", return_value={"objects": {}}):
            result = runner.invoke(template, ["info", "nope", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "error"


class TestTemplateCreateJson:
    def test_create_json(self, tmp_path):
        from o3de_pilot.commands.template import template
        target = tmp_path / "jsontpl"
        runner = CliRunner()
        result = runner.invoke(template, [
            "create", "org.test.tpl.json",
            "--path", str(target), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["name"] == "org.test.tpl.json"

    def test_create_json_exists(self, tmp_path):
        from o3de_pilot.commands.template import template
        target = tmp_path / "exists2"
        target.mkdir()
        runner = CliRunner()
        result = runner.invoke(template, [
            "create", "test", "--path", str(target), "--json",
        ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "error"


class TestTemplateInstanceDryRun:
    def test_instance_dry_run_json(self, tmp_path):
        from o3de_pilot.commands.template import template
        from unittest.mock import MagicMock

        # Mock resolver
        tpl_path = tmp_path / "mytpl"
        tpl_path.mkdir()
        (tpl_path / "Template").mkdir()
        (tpl_path / "Code").mkdir()

        mock_tpl = MagicMock()
        mock_tpl.path = tpl_path

        mock_resolver = MagicMock()
        mock_resolver.templates = {"org.test.tpl": mock_tpl}

        runner = CliRunner()
        with patch("o3de_pilot.core.resolver.Resolver", return_value=mock_resolver):
            result = runner.invoke(template, [
                "instance", "org.test.tpl", "myinst",
                "--path", str(tmp_path / "inst"),
                "--dry-run", "--json",
            ])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["template"] == "org.test.tpl"
        assert "Code" in data["data"]["files"]
        # Verify nothing was actually created
        assert not (tmp_path / "inst").exists()
