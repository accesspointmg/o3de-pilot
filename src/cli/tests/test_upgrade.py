# O3DE Pilot - Upgrade Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.upgrade module."""

import pytest
import tempfile
import json
from pathlib import Path

from o3de_pilot.core.upgrade import (
    get_schema_version,
    needs_upgrade,
    upgrade_0_to_1,
    upgrade_1_to_2,
    upgrade_to_latest,
    _get_json_filename_for_type,
    _ensure_explicit_json_path,
    _strip_embedded_data,
)


class TestGetSchemaVersion:
    """Test get_schema_version function."""
    
    def test_legacy_engine_by_name(self):
        """Should detect legacy engine by engine_name."""
        data = {"engine_name": "o3de", "version": "1.0.0"}
        obj_type, version = get_schema_version(data)
        assert obj_type == "engine"
        assert version == "0"
    
    def test_legacy_project_by_name(self):
        """Should detect legacy project by project_name."""
        data = {"project_name": "MyGame"}
        obj_type, version = get_schema_version(data)
        assert obj_type == "project"
        assert version == "0"
    
    def test_legacy_gem_by_name(self):
        """Should detect legacy gem by gem_name."""
        data = {"gem_name": "MyGem"}
        obj_type, version = get_schema_version(data)
        assert obj_type == "gem"
        assert version == "0"
    
    def test_schema_1_with_url(self):
        """Should parse schema URL for version 1.0."""
        data = {
            "$schema": "https://o3de.org/o3de-gem-1.0.json",
            "gem_name": "MyGem"
        }
        obj_type, version = get_schema_version(data)
        assert obj_type == "gem"
        assert version == "1.0" or version.startswith("1")
    
    def test_schema_2_with_url(self):
        """Should parse schema URL for version 2.0.0."""
        data = {
            "$schema": "https://overlo3de.com/o3de-engine-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "engine": {"name": "org.o3de.engine.core"}
        }
        obj_type, version = get_schema_version(data)
        assert obj_type == "engine"
        assert version == "2.0.0"
    
    def test_unknown_type(self):
        """Should return unknown for unrecognized format."""
        data = {"random_field": "value"}
        obj_type, version = get_schema_version(data)
        assert obj_type == "unknown"


class TestNeedsUpgrade:
    """Test needs_upgrade function."""
    
    def test_legacy_needs_upgrade(self):
        """Legacy (version 0) should need upgrade."""
        data = {"engine_name": "o3de"}
        assert needs_upgrade(data) is True
    
    def test_version_1_needs_upgrade(self):
        """Version 1.0 should need upgrade to 2.0.0."""
        data = {
            "$schema": "https://o3de.org/o3de-gem-1.0.json",
            "$schemaVersion": "1.0"
        }
        assert needs_upgrade(data, "2.0.0") is True
    
    def test_version_2_no_upgrade(self):
        """Version 2.0.0 should not need upgrade."""
        data = {
            "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.o3de.gem.test"}
        }
        assert needs_upgrade(data, "2.0.0") is False
    
    def test_custom_target_version(self):
        """Should respect custom target version."""
        data = {
            "$schema": "https://o3de.org/o3de-gem-1.0.json",
            "$schemaVersion": "1.0"
        }
        assert needs_upgrade(data, "1.0") is False
        assert needs_upgrade(data, "1.5") is True


class TestUpgrade0To1:
    """Test upgrade_0_to_1 function."""
    
    def test_adds_schema_url(self):
        """Should add $schema URL."""
        data = {"engine_name": "o3de"}
        result = upgrade_0_to_1(data, "engine")
        assert "$schema" in result
        assert "o3de-engine" in result["$schema"]
    
    def test_adds_schema_version(self):
        """Should add $schemaVersion."""
        data = {"gem_name": "MyGem"}
        result = upgrade_0_to_1(data, "gem")
        assert result.get("$schemaVersion") == "1.0"
    
    def test_converts_name_to_origin(self):
        """Should convert engine_name to origin.name."""
        data = {
            "engine_name": "o3de",
            "version": "1.0.0",
        }
        result = upgrade_0_to_1(data, "engine")
        assert "origin" in result
        assert result["origin"]["name"] == "o3de"


class TestUpgrade1To2:
    """Test upgrade_1_to_2 function."""
    
    def test_updates_schema_url(self):
        """Should update $schema URL to 2.0.0."""
        data = {
            "$schema": "https://o3de.org/o3de-engine-1.0.json",
            "$schemaVersion": "1.0"
        }
        result = upgrade_1_to_2(data, "engine")
        assert "2.0.0" in result["$schema"]
        assert result.get("$schemaVersion") == "2.0.0"
    
    def test_strips_embedded_children(self):
        """Should strip embedded data from children."""
        data = {
            "$schema": "https://o3de.org/o3de-engine-1.0.json",
            "children": {
                "gems": [
                    {"path": "Gems/Core", "gem_name": "Core"},
                    "Gems/Other"
                ]
            }
        }
        result = upgrade_1_to_2(data, "engine")
        assert result["children"]["gems"] == [
            "Gems/Core/gem.json",
            "Gems/Other/gem.json"
        ]


class TestGetJsonFilenameForType:
    """Test _get_json_filename_for_type function."""
    
    def test_plural_to_singular(self):
        """Should convert plural key to singular filename."""
        assert _get_json_filename_for_type("gems") == "gem.json"
        assert _get_json_filename_for_type("engines") == "engine.json"
        assert _get_json_filename_for_type("projects") == "project.json"
        assert _get_json_filename_for_type("templates") == "template.json"
        assert _get_json_filename_for_type("repos") == "repo.json"
        assert _get_json_filename_for_type("overlays") == "overlay.json"


class TestEnsureExplicitJsonPath:
    """Test _ensure_explicit_json_path function."""
    
    def test_already_explicit(self):
        """Should not modify already explicit paths."""
        path = "Gems/MyGem/gem.json"
        result = _ensure_explicit_json_path(path, "gems")
        assert result == path
    
    def test_adds_json_extension(self):
        """Should add JSON filename."""
        result = _ensure_explicit_json_path("Gems/MyGem", "gems")
        assert result == "Gems/MyGem/gem.json"
    
    def test_strips_trailing_slash(self):
        """Should handle trailing slashes."""
        result = _ensure_explicit_json_path("Gems/MyGem/", "gems")
        assert result == "Gems/MyGem/gem.json"
    
    def test_different_types(self):
        """Should use correct filename for each type."""
        assert _ensure_explicit_json_path("Engines/o3de", "engines") == "Engines/o3de/engine.json"
        assert _ensure_explicit_json_path("Projects/MyGame", "projects") == "Projects/MyGame/project.json"
        assert _ensure_explicit_json_path("Templates/Default", "templates") == "Templates/Default/template.json"


class TestStripEmbeddedData:
    """Test _strip_embedded_data function."""
    
    def test_string_paths(self):
        """Should convert string paths to explicit format."""
        children = {"gems": ["Gems/Core", "Gems/Other"]}
        result = _strip_embedded_data(children)
        assert result == {
            "gems": ["Gems/Core/gem.json", "Gems/Other/gem.json"]
        }
    
    def test_embedded_objects(self):
        """Should extract paths from embedded objects."""
        children = {
            "gems": [
                {"path": "Gems/Core", "gem_name": "Core"},
                {"path": "Gems/Other", "version": "1.0.0"}
            ]
        }
        result = _strip_embedded_data(children)
        assert result == {
            "gems": ["Gems/Core/gem.json", "Gems/Other/gem.json"]
        }
    
    def test_mixed_format(self):
        """Should handle mixed string/object format."""
        children = {
            "gems": [
                "Gems/String",
                {"path": "Gems/Object"}
            ]
        }
        result = _strip_embedded_data(children)
        assert result == {
            "gems": ["Gems/String/gem.json", "Gems/Object/gem.json"]
        }
    
    def test_empty_input(self):
        """Should handle empty/invalid input."""
        assert _strip_embedded_data({}) == {}
        assert _strip_embedded_data(None) == {}
        assert _strip_embedded_data("invalid") == {}
    
    def test_multiple_types(self):
        """Should handle multiple children types."""
        children = {
            "gems": ["Gems/A"],
            "projects": ["Projects/B"],
            "templates": ["Templates/C"]
        }
        result = _strip_embedded_data(children)
        assert result == {
            "gems": ["Gems/A/gem.json"],
            "projects": ["Projects/B/project.json"],
            "templates": ["Templates/C/template.json"]
        }


class TestUpgradeToLatest:
    """Test upgrade_to_latest function."""
    
    def test_upgrade_from_legacy(self):
        """Should upgrade legacy (v0) to latest (v2.0.0)."""
        data = {
            "engine_name": "o3de",
            "version": "1.0.0"
        }
        result = upgrade_to_latest(data, "engine")
        
        assert result.get("$schemaVersion") == "2.0.0"
        # 2.0.0 uses origin wrapper from 1.0 upgrade
        assert "origin" in result
        assert result["origin"]["name"] == "o3de"
    
    def test_upgrade_from_v1(self):
        """Should upgrade v1 to latest (v2.0.0)."""
        data = {
            "$schema": "https://o3de.org/o3de-gem-1.0.json",
            "$schemaVersion": "1.0",
            "gem_name": "MyGem",
            "version": "1.0.0"
        }
        result = upgrade_to_latest(data, "gem")
        
        assert result.get("$schemaVersion") == "2.0.0"
    
    def test_already_latest_passes_through(self):
        """Should pass through already-latest data."""
        data = {
            "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.o3de.gem.test",
                "version": "1.0.0"
            }
        }
        result = upgrade_to_latest(data, "gem")
        
        # Should still be 2.0.0
        assert result.get("$schemaVersion") == "2.0.0"
