# O3DE Pilot - Register Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for register.py — the object registration command."""

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
            "engines": kw.get("engines", []),
            "projects": kw.get("projects", []),
            "gems": kw.get("gems", []),
            "templates": kw.get("templates", []),
            "repos": kw.get("repos", []),
            "overlays": kw.get("overlays", []),
        },
        "remote": {"engines": [], "gems": []},
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


class TestDetectObjectType:
    def test_detect_gem(self, tmp_path):
        from o3de_pilot.commands.register import detect_object_type
        d = tmp_path / "mygem"
        d.mkdir()
        _write_json(d / "gem.json", {"gem": {}})
        assert detect_object_type(d) == "gem"

    def test_detect_engine(self, tmp_path):
        from o3de_pilot.commands.register import detect_object_type
        d = tmp_path / "myeng"
        d.mkdir()
        _write_json(d / "engine.json", {"engine": {}})
        assert detect_object_type(d) == "engine"

    def test_detect_project(self, tmp_path):
        from o3de_pilot.commands.register import detect_object_type
        d = tmp_path / "myproj"
        d.mkdir()
        _write_json(d / "project.json", {"project": {}})
        assert detect_object_type(d) == "project"

    def test_detect_none(self, tmp_path):
        from o3de_pilot.commands.register import detect_object_type
        d = tmp_path / "empty"
        d.mkdir()
        assert detect_object_type(d) is None


class TestResolveToJson:
    def test_resolve_dir(self, tmp_path):
        from o3de_pilot.commands.register import resolve_to_json
        d = _gem_dir(tmp_path, "foo")
        result = resolve_to_json(d)
        assert result is not None
        assert result[1] == "gem"

    def test_resolve_file(self, tmp_path):
        from o3de_pilot.commands.register import resolve_to_json
        d = _gem_dir(tmp_path, "bar")
        result = resolve_to_json(d / "gem.json")
        assert result is not None
        assert result[1] == "gem"

    def test_resolve_typed(self, tmp_path):
        from o3de_pilot.commands.register import resolve_to_json
        d = _gem_dir(tmp_path, "baz")
        result = resolve_to_json(d, "gem")
        assert result is not None

    def test_resolve_wrong_type(self, tmp_path):
        from o3de_pilot.commands.register import resolve_to_json
        d = _gem_dir(tmp_path, "qux")
        result = resolve_to_json(d, "engine")
        assert result is None

    def test_resolve_nonexistent(self, tmp_path):
        from o3de_pilot.commands.register import resolve_to_json
        result = resolve_to_json(tmp_path / "nope")
        assert result is None


class TestRegisterObjectPath:
    def test_add(self, tmp_path):
        from o3de_pilot.commands.register import register_object_path
        manifest = {"local": {"gems": []}}
        jp = tmp_path / "gem.json"
        jp.write_text("{}")
        changed = register_object_path(manifest, jp, "gem")
        assert changed is True
        assert len(manifest["local"]["gems"]) == 1

    def test_add_duplicate(self, tmp_path):
        from o3de_pilot.commands.register import register_object_path
        jp = tmp_path / "gem.json"
        jp.write_text("{}")
        manifest = {"local": {"gems": [jp.as_posix()]}}
        changed = register_object_path(manifest, jp, "gem")
        assert changed is False

    def test_remove(self, tmp_path):
        from o3de_pilot.commands.register import register_object_path
        jp = tmp_path / "gem.json"
        jp.write_text("{}")
        manifest = {"local": {"gems": [jp.as_posix()]}}
        changed = register_object_path(manifest, jp, "gem", remove=True)
        assert changed is True
        assert len(manifest["local"]["gems"]) == 0

    def test_remove_not_present(self, tmp_path):
        from o3de_pilot.commands.register import register_object_path
        manifest = {"local": {"gems": []}}
        jp = tmp_path / "gem.json"
        jp.write_text("{}")
        changed = register_object_path(manifest, jp, "gem", remove=True)
        assert changed is False


class TestIsDirectlyRegistered:
    def test_registered(self, tmp_path):
        from o3de_pilot.commands.register import is_directly_registered
        d = _gem_dir(tmp_path, "reg")
        manifest = {"local": {"gems": [(d / "gem.json").as_posix()]}}
        assert is_directly_registered(d, manifest) is True

    def test_not_registered(self, tmp_path):
        from o3de_pilot.commands.register import is_directly_registered
        manifest = {"local": {"gems": []}}
        assert is_directly_registered(tmp_path / "nope", manifest) is False


class TestIsChildOfRegistered:
    def test_child(self, tmp_path):
        from o3de_pilot.commands.register import is_child_of_registered
        parent = _gem_dir(tmp_path, "parent")
        child_path = parent / "child"
        child_path.mkdir()
        manifest = {"local": {"gems": [(parent / "gem.json").as_posix()]}}
        result = is_child_of_registered(child_path, manifest)
        assert result is not None

    def test_not_child(self, tmp_path):
        from o3de_pilot.commands.register import is_child_of_registered
        d = _gem_dir(tmp_path, "standalone")
        manifest = {"local": {"gems": []}}
        assert is_child_of_registered(d, manifest) is None


class TestRegisterCommand:
    def test_register_local_gem(self, tmp_path):
        from o3de_pilot.commands.register import register
        d = _gem_dir(tmp_path, "mygem")
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.register.ensure_manifest_2", return_value=mp):
            result = runner.invoke(register, [str(d)])
        assert result.exit_code == 0
        assert "Registered" in result.output

    def test_register_remote(self, tmp_path):
        from o3de_pilot.commands.register import register
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path", return_value=mp):
            result = runner.invoke(register, [
                "https://example.com/gem.json", "--remote"
            ])
        assert result.exit_code == 0
        data = json.loads(mp.read_text())
        assert "https://example.com/gem.json" in data["remote"]["gems"]

    def test_register_nonexistent_path(self, tmp_path):
        from o3de_pilot.commands.register import register
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path", return_value=mp):
            result = runner.invoke(register, [str(tmp_path / "nope")])
        assert result.exit_code != 0

    def test_register_no_json(self, tmp_path):
        from o3de_pilot.commands.register import register
        empty = tmp_path / "empty"
        empty.mkdir()
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path", return_value=mp):
            result = runner.invoke(register, [str(empty)])
        assert result.exit_code != 0

    def test_register_already_registered(self, tmp_path):
        from o3de_pilot.commands.register import register
        d = _gem_dir(tmp_path, "dup")
        mp = _manifest(tmp_path, gems=[(d / "gem.json").as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path", return_value=mp):
            result = runner.invoke(register, [str(d)])
        assert "Already" in result.output or "already" in result.output


class TestUnregisterCommand:
    def test_unregister_local(self, tmp_path):
        from o3de_pilot.commands.register import unregister
        d = _gem_dir(tmp_path, "unreg")
        mp = _manifest(tmp_path, gems=[(d / "gem.json").as_posix()])
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path", return_value=mp):
            result = runner.invoke(unregister, [str(d)])
        assert "Unregistered" in result.output

    def test_unregister_not_found(self, tmp_path):
        from o3de_pilot.commands.register import unregister
        mp = _manifest(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path", return_value=mp):
            result = runner.invoke(unregister, [str(tmp_path / "nope")])
        assert "Not registered" in result.output or "not found" in result.output.lower()

    def test_unregister_remote(self, tmp_path):
        from o3de_pilot.commands.register import unregister
        mp = _manifest(tmp_path)
        data = json.loads(mp.read_text())
        data["remote"]["gems"] = ["https://example.com/gem.json"]
        mp.write_text(json.dumps(data))
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path", return_value=mp):
            result = runner.invoke(unregister, [
                "https://example.com/gem.json", "--remote"
            ])
        assert "Unregistered" in result.output

    def test_unregister_no_manifest(self, tmp_path):
        from o3de_pilot.commands.register import unregister
        runner = CliRunner()
        with patch("o3de_pilot.commands.register.get_manifest_path",
                    return_value=tmp_path / "nope.json"):
            result = runner.invoke(unregister, ["something"])
        assert result.exit_code != 0


class TestCheckAndUpgrade:
    def test_already_at_200(self, tmp_path):
        from o3de_pilot.commands.register import check_and_upgrade_object
        d = _gem_dir(tmp_path, "upg")
        result = check_and_upgrade_object(d, "gem")
        assert result is True

    def test_unknown_type(self, tmp_path):
        from o3de_pilot.commands.register import check_and_upgrade_object
        result = check_and_upgrade_object(tmp_path, "unknown_type")
        assert result is False
