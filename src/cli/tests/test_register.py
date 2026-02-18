# O3DE Pilot CLI - Register Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.commands.register module."""

import pytest
import json
import tempfile
from pathlib import Path
from click.testing import CliRunner

from o3de_pilot.commands.register import (
    detect_object_type,
    check_and_upgrade_object,
    register_object_path,
    OBJECT_JSON_FILES,
)
from o3de_pilot.__main__ import cli


class TestDetectObjectType:
    """Test object type detection from directory contents."""
    
    def test_detect_engine(self, tmp_path):
        """Should detect engine from engine.json."""
        (tmp_path / "engine.json").write_text('{"engine_name": "test"}')
        assert detect_object_type(tmp_path) == "engine"
    
    def test_detect_project(self, tmp_path):
        """Should detect project from project.json."""
        (tmp_path / "project.json").write_text('{"project_name": "test"}')
        assert detect_object_type(tmp_path) == "project"
    
    def test_detect_gem(self, tmp_path):
        """Should detect gem from gem.json."""
        (tmp_path / "gem.json").write_text('{"gem_name": "test"}')
        assert detect_object_type(tmp_path) == "gem"
    
    def test_detect_template(self, tmp_path):
        """Should detect template from template.json."""
        (tmp_path / "template.json").write_text('{"template_name": "test"}')
        assert detect_object_type(tmp_path) == "template"
    
    def test_detect_repo(self, tmp_path):
        """Should detect repo from repo.json."""
        (tmp_path / "repo.json").write_text('{"repo_name": "test"}')
        assert detect_object_type(tmp_path) == "repo"
    
    def test_detect_overlay(self, tmp_path):
        """Should detect overlay from overlay.json."""
        (tmp_path / "overlay.json").write_text('{"overlay_name": "test"}')
        assert detect_object_type(tmp_path) == "overlay"
    
    def test_no_object_json(self, tmp_path):
        """Should return None if no object JSON found."""
        (tmp_path / "random.txt").write_text("hello")
        assert detect_object_type(tmp_path) is None
    
    def test_empty_directory(self, tmp_path):
        """Should return None for empty directory."""
        assert detect_object_type(tmp_path) is None
    
    def test_priority_engine_first(self, tmp_path):
        """Should return first matching type based on dict order."""
        # Create multiple JSON files - engine should be found first based on OBJECT_JSON_FILES order
        (tmp_path / "engine.json").write_text('{"engine_name": "test"}')
        (tmp_path / "gem.json").write_text('{"gem_name": "test"}')
        result = detect_object_type(tmp_path)
        assert result == "engine"


class TestCheckAndUpgradeObject:
    """Test schema upgrade functionality."""
    
    def test_already_at_2_0_0(self, tmp_path):
        """Should return True without creating sidecar for 2.0.0 objects."""
        # Put 2.0.0 content directly in the sidecar file
        sidecar = tmp_path / "gem.2-0-0.json"
        data = {
            "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.test.gem.mygem",
                "version": "1.0.0"
            }
        }
        sidecar.write_text(json.dumps(data))
        
        result = check_and_upgrade_object(tmp_path, "gem")
        assert result is True
    
    def test_upgrade_legacy_gem(self, tmp_path):
        """Should upgrade legacy gem to 2.0.0 (sidecar)."""
        gem_json = tmp_path / "gem.json"
        data = {
            "gem_name": "MyGem",
            "version": "1.0.0",
            "display_name": "My Gem"
        }
        gem_json.write_text(json.dumps(data))
        
        result = check_and_upgrade_object(tmp_path, "gem")
        assert result is True
        
        # Verify sidecar was created with upgraded content
        sidecar = tmp_path / "gem.2-0-0.json"
        assert sidecar.exists()
        with open(sidecar) as f:
            upgraded = json.load(f)
        assert upgraded.get("$schemaVersion") == "2.0.0"
    
    def test_upgrade_legacy_engine(self, tmp_path):
        """Should upgrade legacy engine to 2.0.0 (sidecar)."""
        engine_json = tmp_path / "engine.json"
        data = {
            "engine_name": "TestEngine",
            "version": "2.0.0"
        }
        engine_json.write_text(json.dumps(data))
        
        result = check_and_upgrade_object(tmp_path, "engine")
        assert result is True
        
        # Verify sidecar was created
        sidecar = tmp_path / "engine.2-0-0.json"
        assert sidecar.exists()
        with open(sidecar) as f:
            upgraded = json.load(f)
        assert upgraded.get("$schemaVersion") == "2.0.0"
    
    def test_invalid_json(self, tmp_path):
        """Should return False for invalid JSON."""
        gem_json = tmp_path / "gem.json"
        gem_json.write_text("not valid json {{{")
        
        result = check_and_upgrade_object(tmp_path, "gem")
        assert result is False
    
    def test_missing_json(self, tmp_path):
        """Should return False if JSON file doesn't exist."""
        result = check_and_upgrade_object(tmp_path, "gem")
        assert result is False
    
    def test_unknown_type(self, tmp_path):
        """Should return False for unknown object type."""
        result = check_and_upgrade_object(tmp_path, "invalid_type")
        assert result is False


class TestRegisterObjectPath:
    """Test object path registration in manifest."""
    
    def test_add_engine_path(self, tmp_path):
        """Should add engine path to local.engines."""
        manifest = {}
        result = register_object_path(manifest, tmp_path / "Engines/o3de", "engine")
        
        assert result is True
        assert "local" in manifest
        assert "engines" in manifest["local"]
        assert len(manifest["local"]["engines"]) == 1
    
    def test_add_gem_path(self, tmp_path):
        """Should add gem path to local.gems."""
        manifest = {}
        result = register_object_path(manifest, tmp_path / "Gems/MyGem", "gem")
        
        assert result is True
        assert manifest["local"]["gems"]
    
    def test_add_project_path(self, tmp_path):
        """Should add project path to local.projects."""
        manifest = {}
        result = register_object_path(manifest, tmp_path / "Projects/MyGame", "project")
        
        assert result is True
        assert manifest["local"]["projects"]
    
    def test_remove_path(self, tmp_path):
        """Should remove existing path."""
        obj_path = tmp_path / "Gems/MyGem"
        manifest = {
            "local": {
                "gems": [str(obj_path)]
            }
        }
        
        result = register_object_path(manifest, obj_path, "gem", remove=True)
        assert result is True
        assert manifest["local"]["gems"] == []
    
    def test_remove_nonexistent_path(self, tmp_path):
        """Should return False when removing nonexistent path."""
        manifest = {"local": {"gems": []}}
        result = register_object_path(
            manifest, 
            tmp_path / "Gems/NonExistent", 
            "gem", 
            remove=True
        )
        assert result is False
    
    def test_no_duplicate_registration(self, tmp_path):
        """Should not add duplicate paths."""
        obj_path = tmp_path / "Gems/MyGem"
        manifest = {
            "local": {
                "gems": [str(obj_path)]
            }
        }
        
        # Try to add same path again
        register_object_path(manifest, obj_path, "gem")
        
        # Should still only have one entry
        assert len(manifest["local"]["gems"]) == 1
    
    def test_multiple_gems(self, tmp_path):
        """Should support multiple gem registrations."""
        manifest = {}
        
        register_object_path(manifest, tmp_path / "Gems/Gem1", "gem")
        register_object_path(manifest, tmp_path / "Gems/Gem2", "gem")
        register_object_path(manifest, tmp_path / "Gems/Gem3", "gem")
        
        assert len(manifest["local"]["gems"]) == 3


class TestRegisterCLI:
    """Test register CLI commands."""
    
    def test_register_help(self):
        """Test register --help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["register", "--help"])
        assert result.exit_code == 0
        assert "Register" in result.output
    
    def test_unregister_help(self):
        """Test unregister --help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["unregister", "--help"])
        assert result.exit_code == 0


class TestSchemaVersionDetection:
    """Test schema version detection for registration."""
    
    def test_no_schema_version_is_0(self, tmp_path):
        """Files without $schemaVersion should be detected as 0."""
        from o3de_pilot.core.upgrade import get_schema_version
        
        data = {"gem_name": "LegacyGem", "version": "1.0.0"}
        _, version = get_schema_version(data)
        assert version == "0"
    
    def test_schema_version_1_0(self, tmp_path):
        """Should detect schema version 1.0."""
        from o3de_pilot.core.upgrade import get_schema_version
        
        data = {
            "$schema": "https://o3de.org/o3de-gem-1.0.json",
            "$schemaVersion": "1.0",
            "gem_name": "Gem1"
        }
        _, version = get_schema_version(data)
        assert version.startswith("1")
    
    def test_schema_version_2_0_0(self, tmp_path):
        """Should detect schema version 2.0.0."""
        from o3de_pilot.core.upgrade import get_schema_version
        
        data = {
            "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.gem"}
        }
        _, version = get_schema_version(data)
        assert version == "2.0.0"


class TestUpgradeFlow:
    """Test full upgrade flow for registration."""
    
    def test_upgrade_creates_sidecar(self, tmp_path):
        """Upgrade should create sidecar file, not modify original."""
        from o3de_pilot.core.upgrade import upgrade_file
        
        gem_json = tmp_path / "gem.json"
        data = {"gem_name": "SidecarTest", "version": "1.0.0"}
        gem_json.write_text(json.dumps(data))
        
        result = upgrade_file(gem_json)
        
        # Sidecar should exist
        sidecar = tmp_path / "gem.2-0-0.json"
        assert sidecar.exists()
        assert result[0] == sidecar
        
        # Original should be untouched
        with open(gem_json) as f:
            original = json.load(f)
        assert "$schemaVersion" not in original
    
    def test_upgrade_chain_0_to_2(self, tmp_path):
        """Should upgrade from 0 → 1.0 → 2.0.0 in chain."""
        from o3de_pilot.core.upgrade import upgrade_to_latest, get_schema_version
        
        data = {
            "engine_name": "ChainTest",
            "version": "1.0.0"
        }
        
        result = upgrade_to_latest(data, "engine")
        
        _, version = get_schema_version(result)
        assert version == "2.0.0"
    
    def test_idempotent_upgrade(self, tmp_path):
        """Upgrading already-2.0.0 should be idempotent."""
        from o3de_pilot.core.upgrade import upgrade_to_latest, needs_upgrade
        
        data = {
            "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.gem.idempotent", "version": "1.0.0"}
        }
        
        assert needs_upgrade(data, "2.0.0") is False
        
        result = upgrade_to_latest(data, "gem")
        assert result.get("$schemaVersion") == "2.0.0"
