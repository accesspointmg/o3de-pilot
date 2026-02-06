# O3DE Pilot - Upgrade Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.upgrade module - following O3DE upgrade_schema.py patterns."""

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
    is_reverse_domain_format,
    get_canonical_tag,
    is_url,
)


class TestHelperFunctions:
    """Test helper functions."""
    
    def test_is_reverse_domain_format(self):
        """Should detect reverse domain format."""
        assert is_reverse_domain_format("org.o3de.gem.foo") is True
        assert is_reverse_domain_format("com.company.gem.bar") is True
        assert is_reverse_domain_format("me.home.manifest.default") is True
        assert is_reverse_domain_format("MyGem") is False
        assert is_reverse_domain_format("my-gem") is False
        assert is_reverse_domain_format("") is False
        assert is_reverse_domain_format("single.segment") is False
    
    def test_get_canonical_tag(self):
        """Should return canonical tag names."""
        assert get_canonical_tag("engine") == "Engine"
        assert get_canonical_tag("gem") == "Gem"
        assert get_canonical_tag("project") == "Project"
        assert get_canonical_tag("Engine") == "Engine"  # case insensitive
        assert get_canonical_tag("GEM") == "Gem"
        assert get_canonical_tag("invalid") is None
    
    def test_is_url(self):
        """Should detect URLs."""
        assert is_url("https://example.com") is True
        assert is_url("http://example.com") is True
        assert is_url("ftp://files.example.com") is True
        assert is_url("Gems/MyGem") is False
        assert is_url("/absolute/path") is False


class TestGetSchemaVersion:
    """Test get_schema_version function."""
    
    def test_legacy_engine_by_name(self):
        """Should detect legacy engine by engine_name (no $schemaVersion = v0)."""
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
    
    def test_legacy_manifest(self):
        """Should detect legacy manifest by o3de_manifest_name."""
        data = {"o3de_manifest_name": "user"}
        obj_type, version = get_schema_version(data)
        assert obj_type == "manifest"
        assert version == "0"
    
    def test_legacy_repo(self):
        """Should detect legacy repo by repo_name."""
        data = {"repo_name": "community"}
        obj_type, version = get_schema_version(data)
        assert obj_type == "repo"
        assert version == "0"
    
    def test_legacy_template(self):
        """Should detect legacy template by template_name."""
        data = {"template_name": "DefaultProject"}
        obj_type, version = get_schema_version(data)
        assert obj_type == "template"
        assert version == "0"
    
    def test_legacy_restricted(self):
        """Should detect legacy restricted by restricted_name."""
        data = {"restricted_name": "Jasper"}
        obj_type, version = get_schema_version(data)
        assert obj_type == "restricted"
        assert version == "0"
    
    def test_version_1_with_schema_version(self):
        """Should detect v1.0.0 from $schemaVersion."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem"
        }
        obj_type, version = get_schema_version(data)
        assert obj_type == "gem"
        assert version == "1.0.0"
    
    def test_schema_2_with_url(self):
        """Should parse schema URL for version 2.0.0."""
        data = {
            "$schema": "https://canonical.o3de.org/o3de-engine-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "engine": {"name": "org.o3de.engine.o3de"}
        }
        obj_type, version = get_schema_version(data)
        assert obj_type == "engine"
        assert version == "2.0.0"
    
    def test_schema_2_gem_nested(self):
        """Should detect v2 gem with nested structure."""
        data = {
            "$schemaVersion": "2.0.0",
            "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
            "gem": {"name": "org.o3de.gem.core", "version": "1.0.0"}
        }
        obj_type, version = get_schema_version(data)
        assert obj_type == "gem"
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
        """Version 1.0.0 should need upgrade to 2.0.0."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem"
        }
        assert needs_upgrade(data, "2.0.0") is True
    
    def test_version_2_no_upgrade(self):
        """Version 2.0.0 should not need upgrade."""
        data = {
            "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.o3de.gem.test"}
        }
        assert needs_upgrade(data, "2.0.0") is False
    
    def test_custom_target_version(self):
        """Should respect custom target version."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem"
        }
        assert needs_upgrade(data, "1.0.0") is False
        assert needs_upgrade(data, "1.5") is True


class TestUpgrade0To1:
    """Test upgrade_0_to_1 function - O3DE compatible."""
    
    def test_adds_schema_version(self):
        """Should add $schemaVersion: 1.0.0."""
        data = {"gem_name": "MyGem"}
        result = upgrade_0_to_1(data, "gem")
        assert result.get("$schemaVersion") == "1.0.0"
    
    def test_keeps_engine_name(self):
        """Should keep engine_name field (not convert to origin)."""
        data = {"engine_name": "o3de", "version": "1.0.0"}
        result = upgrade_0_to_1(data, "engine")
        assert "engine_name" in result
        assert result["engine_name"] == "o3de"
    
    def test_keeps_gem_name(self):
        """Should keep gem_name field."""
        data = {"gem_name": "MyGem", "version": "2.0.0"}
        result = upgrade_0_to_1(data, "gem")
        assert "gem_name" in result
        assert result["gem_name"] == "MyGem"
    
    def test_keeps_project_name(self):
        """Should keep project_name field."""
        data = {"project_name": "MyProject"}
        result = upgrade_0_to_1(data, "project")
        assert "project_name" in result
        assert result["project_name"] == "MyProject"
    
    def test_normalizes_uri_fields(self):
        """Should normalize url/uri to {type}_uri."""
        data = {"gem_name": "MyGem", "url": "https://example.com"}
        result = upgrade_0_to_1(data, "gem")
        assert result.get("gem_uri") == "https://example.com"
    
    def test_adds_version_default(self):
        """Should add version: 0.0.0 if missing."""
        data = {"gem_name": "MyGem"}
        result = upgrade_0_to_1(data, "gem")
        assert result.get("version") == "0.0.0"
    
    def test_adds_display_name(self):
        """Should add display_name from name field."""
        data = {"gem_name": "MyGem", "name": "My Gem Display"}
        result = upgrade_0_to_1(data, "gem")
        assert result.get("display_name") == "My Gem Display"
    
    def test_adds_summary(self):
        """Should add summary from description."""
        data = {"gem_name": "MyGem", "description": "A cool gem"}
        result = upgrade_0_to_1(data, "gem")
        assert result.get("summary") == "A cool gem"
    
    def test_adds_last_updated(self):
        """Should add last_updated timestamp."""
        data = {"gem_name": "MyGem"}
        result = upgrade_0_to_1(data, "gem")
        assert "last_updated" in result
    
    def test_preserves_collections(self):
        """Should preserve gems, projects, etc. collections."""
        data = {
            "engine_name": "o3de",
            "gems": ["Gems/Core", "Gems/Other"],
            "projects": ["Projects/Test"]
        }
        result = upgrade_0_to_1(data, "engine")
        assert result.get("gems") == ["Gems/Core", "Gems/Other"]
        assert result.get("projects") == ["Projects/Test"]
    
    def test_preserves_source_control(self):
        """Should preserve source control fields."""
        data = {
            "gem_name": "MyGem",
            "source_control_uri": "https://github.com/o3de/mygem"
        }
        result = upgrade_0_to_1(data, "gem")
        assert result.get("source_control_uri") == "https://github.com/o3de/mygem"


class TestUpgrade1To2:
    """Test upgrade_1_to_2 function - O3DE compatible."""
    
    def test_updates_schema_version(self):
        """Should update $schemaVersion to 2.0.0."""
        data = {"$schemaVersion": "1.0.0", "gem_name": "MyGem"}
        result = upgrade_1_to_2(data, "gem")
        assert result["$schemaVersion"] == "2.0.0"
    
    def test_adds_schema_url(self):
        """Should add $schema URL for canonical.o3de.org."""
        data = {"$schemaVersion": "1.0.0", "gem_name": "MyGem"}
        result = upgrade_1_to_2(data, "gem")
        assert "canonical.o3de.org" in result["$schema"]
        assert "o3de-gem-2.0.0.json" in result["$schema"]
    
    def test_nests_gem_properties(self):
        """Should nest gem properties under gem key."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "version": "1.2.3",
            "display_name": "My Gem"
        }
        result = upgrade_1_to_2(data, "gem")
        assert "gem" in result
        assert result["gem"]["version"] == "1.2.3"
        assert result["gem"]["display_name"] == "My Gem"
    
    def test_converts_to_reverse_domain(self):
        """Should convert simple name to reverse domain format."""
        data = {"$schemaVersion": "1.0.0", "gem_name": "MyGem"}
        result = upgrade_1_to_2(data, "gem")
        assert result["gem"]["name"] == "org.o3de.gem.mygem"
    
    def test_preserves_reverse_domain(self):
        """Should preserve existing reverse domain names."""
        data = {
            "$schemaVersion": "1.0.0", 
            "gem_name": "com.company.gem.special"
        }
        result = upgrade_1_to_2(data, "gem")
        assert result["gem"]["name"] == "com.company.gem.special"
    
    def test_creates_origin_structure(self):
        """Should create origin structure."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "origin": "Open 3D Engine - o3de.org"
        }
        result = upgrade_1_to_2(data, "gem")
        assert "origin" in result
        assert result["origin"]["name"] == "Open 3D Engine - o3de.org"
    
    def test_creates_licenses_for_o3de(self):
        """Should create O3DE licenses for o3de objects."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "O3DECore",
            "origin": "Open 3D Engine - o3de.org"
        }
        result = upgrade_1_to_2(data, "gem")
        assert "licenses" in result
        assert len(result["licenses"]) >= 1
    
    def test_creates_tags_structure(self):
        """Should create tags.canonical and tags.user."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "user_tags": ["tools", "editor"]
        }
        result = upgrade_1_to_2(data, "gem")
        assert "tags" in result
        assert "canonical" in result["tags"]
        assert "user" in result["tags"]
        assert "Gem" in result["tags"]["canonical"]
        assert "tools" in result["tags"]["user"]
    
    def test_creates_icon_structure(self):
        """Should create icon.relative_path and icon.uri."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "icon_path": "preview.png",
            "icon_url": "https://example.com/icon.png"
        }
        result = upgrade_1_to_2(data, "gem")
        assert result["icon"]["relative_path"] == "preview.png"
        assert result["icon"]["uri"] == "https://example.com/icon.png"
    
    def test_creates_documentation_structure(self):
        """Should create documentation structure."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "documentation_url": "https://docs.example.com"
        }
        result = upgrade_1_to_2(data, "gem")
        assert result["documentation"]["uri"] == "https://docs.example.com"
    
    def test_splits_children_and_remote(self):
        """Should split local/remote collections."""
        data = {
            "$schemaVersion": "1.0.0",
            "engine_name": "o3de",
            "gems": [
                "Gems/Local",
                "https://github.com/o3de/remote.git"
            ]
        }
        result = upgrade_1_to_2(data, "engine")
        assert "children" in result
        assert "remote" in result
        assert any("Local" in p for p in result["children"]["gems"])
        assert "https://github.com/o3de/remote.git" in result["remote"]["gems"]
    
    def test_converts_external_subdirectories_to_gems(self):
        """Should convert external_subdirectories to children.gems."""
        data = {
            "$schemaVersion": "1.0.0",
            "project_name": "MyProject",
            "external_subdirectories": ["Gems/SubGem"]
        }
        result = upgrade_1_to_2(data, "project")
        assert any("SubGem" in p for p in result["children"]["gems"])
    
    def test_creates_source_control_structure(self):
        """Should restructure source_control fields."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "source_control_uri": "https://github.com/org/repo",
            "source_control_branch": "main"
        }
        result = upgrade_1_to_2(data, "gem")
        assert "source_control" in result
        assert result["source_control"]["git_uri"] == "https://github.com/org/repo.git"
        assert result["source_control"]["branch"] == "main"
    
    def test_creates_download_structure(self):
        """Should restructure download fields."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "download_source_uri": "https://example.com/gem",
            "sha256": "abc123"
        }
        result = upgrade_1_to_2(data, "gem")
        assert "download" in result
        assert result["download"]["source_zip_uri"] == "https://example.com/gem.zip"
        assert result["download"]["source_zip_sha256"] == "abc123"
    
    def test_creates_dependent_gems(self):
        """Should convert gem_names to dependent.gems with version specifiers."""
        data = {
            "$schemaVersion": "1.0.0",
            "project_name": "MyProject",
            "gem_names": ["Core", "Physics"]
        }
        result = upgrade_1_to_2(data, "project")
        assert "dependent" in result
        assert "gems" in result["dependent"]
        assert "org.o3de.gem.core>=0.0.0" in result["dependent"]["gems"]
        assert "org.o3de.gem.physics>=0.0.0" in result["dependent"]["gems"]
    
    def test_adds_default_platforms(self):
        """Should add default platforms list."""
        data = {"$schemaVersion": "1.0.0", "gem_name": "MyGem"}
        result = upgrade_1_to_2(data, "gem")
        assert "platforms" in result
        assert "Windows" in result["platforms"]
        assert "Linux" in result["platforms"]
    
    def test_preserves_existing_platforms(self):
        """Should preserve existing platforms."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "platforms": ["Xbox", "PlayStation"]
        }
        result = upgrade_1_to_2(data, "gem")
        assert result["platforms"] == ["Xbox", "PlayStation"]
    
    def test_engine_nested_structure(self):
        """Should create origin structure with name, version, type."""
        data = {
            "$schemaVersion": "1.0.0",
            "engine_name": "o3de",
            "version": "2.0.0",
            "O3DEVersion": "24.09.0"
        }
        result = upgrade_1_to_2(data, "engine")
        assert "origin" in result
        assert result["origin"]["name"] == "o3de"
        assert result["origin"]["version"] == "2.0.0"
        assert result["origin"]["type"] == "engine"
        assert result["O3DEVersion"] == "24.09.0"
    
    def test_project_engine_reference(self):
        """Should convert engine reference to version specifier."""
        data = {
            "$schemaVersion": "1.0.0",
            "project_name": "MyGame",
            "engine": "o3de"
        }
        result = upgrade_1_to_2(data, "project")
        assert result["engine"] == "org.o3de.engine.o3de>=1.0.0"


class TestUpgradeToLatest:
    """Test upgrade_to_latest function."""
    
    def test_upgrade_from_legacy_to_2(self):
        """Should upgrade legacy (v0) all the way to v2.0.0."""
        data = {
            "engine_name": "o3de",
            "version": "1.0.0"
        }
        result = upgrade_to_latest(data, "engine")
        
        assert result.get("$schemaVersion") == "2.0.0"
        # 2.0.0 uses origin for identity
        assert "origin" in result
        assert result["origin"]["name"] == "o3de"
        assert result["origin"]["version"] == "1.0.0"
        assert result["origin"]["type"] == "engine"
    
    def test_upgrade_from_v1_to_2(self):
        """Should upgrade v1 to v2.0.0."""
        data = {
            "$schemaVersion": "1.0.0",
            "gem_name": "MyGem",
            "version": "1.0.0"
        }
        result = upgrade_to_latest(data, "gem")
        
        assert result.get("$schemaVersion") == "2.0.0"
        assert "gem" in result
        assert result["gem"]["name"] == "org.o3de.gem.mygem"
    
    def test_already_latest_passes_through(self):
        """Should pass through already-latest data."""
        data = {
            "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "gem": {
                "name": "org.o3de.gem.test",
                "version": "1.0.0"
            }
        }
        result = upgrade_to_latest(data, "gem")
        
        assert result.get("$schemaVersion") == "2.0.0"
        assert result["gem"]["name"] == "org.o3de.gem.test"
    
    def test_auto_detects_type(self):
        """Should auto-detect object type if not provided."""
        data = {"gem_name": "AutoDetect", "version": "1.0.0"}
        result = upgrade_to_latest(data)
        
        assert "gem" in result
        assert result["gem"]["name"] == "org.o3de.gem.autodetect"


class TestManifestUpgrade:
    """Test manifest-specific upgrade path."""
    
    def test_manifest_0_to_1(self):
        """Should upgrade manifest from v0 to v1."""
        data = {
            "o3de_manifest_name": "user",
            "default_engines_folder": "/path/to/engines"
        }
        result = upgrade_0_to_1(data, "manifest")
        assert result["$schemaVersion"] == "1.0.0"
        assert result["o3de_manifest_name"] == "user"
        assert result["default_engines_folder"] == "/path/to/engines"
    
    def test_manifest_1_to_2(self):
        """Should upgrade manifest from v1 to v2."""
        data = {
            "$schemaVersion": "1.0.0",
            "o3de_manifest_name": "user",
            "default_engines_folder": "/path/to/engines",
            "engines": ["/local/engine", "https://remote.com/engine.json"]
        }
        result = upgrade_1_to_2(data, "manifest")
        assert result["$schemaVersion"] == "2.0.0"
        assert "o3de_manifest" in result
        assert result["o3de_manifest"]["name"] == "me.home.manifest.user"
        assert "default" in result
        assert result["default"]["engines_path"] == "/path/to/engines"
        assert "local" in result
        assert "remote" in result


class TestRestrictedUpgrade:
    """Test restricted-specific upgrade path."""
    
    def test_restricted_0_to_1(self):
        """Should upgrade restricted from v0 to v1."""
        data = {
            "restricted_name": "Jasper",
            "extends": "engine",
            "precedence": 100
        }
        result = upgrade_0_to_1(data, "restricted")
        assert result["$schemaVersion"] == "1.0.0"
        assert result["restricted_name"] == "Jasper"
        assert result["extends"] == "engine"
        assert result["precedence"] == 100
    
    def test_restricted_1_to_2(self):
        """Should upgrade restricted from v1 to v2."""
        data = {
            "$schemaVersion": "1.0.0",
            "restricted_name": "Jasper",
            "extends": "engine",
            "precedence": 100,
            "platform_maps": []
        }
        result = upgrade_1_to_2(data, "restricted")
        assert result["$schemaVersion"] == "2.0.0"
        assert "restricted" in result
        assert result["restricted"]["name"] == "org.o3de.restricted.jasper"
        assert result["extends"] == "engine"
        assert result["precedence"] == 100
        # Restricted objects have empty platforms by default
        assert result["platforms"] == []


class TestRealisticEngineUpgrade:
    """Test engine upgrade with realistic O3DE data."""
    
    def test_o3de_engine_full_upgrade(self):
        """Should upgrade realistic O3DE engine.json from v0 to v2."""
        # Based on actual F:\github\byrcolin\o3de\engine.json
        data = {
            "O3DEVersion": "4.2.0",
            "engine_name": "o3de",
            "display_name": "Open 3D Engine",
            "version": "4.2.0",
            "api_versions": "graphics:2.2;physics:2.2;terrain:1.1;prefab:1.2;shadermodel:3.0;script:1.3;animation:1.2;aws:1.2;multiplayer:1.3",
            "external_subdirectories": ["Gems/Archive", "Gems/Atom"],
            "templates": ["Templates/DefaultProject"],
            "copyright_year": "2021",
            "copyright_text": "Copyright (c) Contributors to the Open 3D Engine Project",
            "license": "Apache-2.0-Or-MIT",
            "license_url": "https://www.o3de.org/license/",
            "origin": "Open 3D Engine - o3de.org",
            "origin_url": "https://www.o3de.org/",
            "documentation_url": "https://www.o3de.org/docs/"
        }
        result = upgrade_to_latest(data, "engine")
        
        # Check schema
        assert result["$schemaVersion"] == "2.0.0"
        assert "canonical.o3de.org" in result["$schema"]
        assert "o3de-engine-2.0.0.json" in result["$schema"]
        
        # Check origin structure (engines use origin, not nested engine)
        assert result["origin"]["name"] == "o3de"
        assert result["origin"]["version"] == "4.2.0"
        assert result["origin"]["type"] == "engine"
        
        # Check O3DEVersion preserved
        assert result["O3DEVersion"] == "4.2.0"
        
        # Check api_versions preserved
        assert "api_versions" in result
        
        # Check children
        assert "children" in result
        assert any("Gems/Archive" in p for p in result["children"]["gems"])
        assert "Templates/DefaultProject/template.json" in result["children"]["templates"]
        
        # Note: Engine upgrade is simplified - doesn't add licenses/docs structure
        # Those fields could be added in future upgrade iterations


class TestRealisticGemUpgrade:
    """Test gem upgrade with realistic O3DE data."""
    
    def test_achievements_gem_upgrade(self):
        """Should upgrade realistic Achievements gem from v0 to v2."""
        data = {
            "gem_name": "Achievements",
            "display_name": "Achievements",
            "license": "Apache-2.0 OR MIT",
            "license_url": "https://github.com/o3de/o3de/blob/development/LICENSE.txt",
            "origin": "Open 3D Engine - o3de.org",
            "origin_url": "https://www.o3de.org",
            "type": "Code",
            "summary": "The Achievements Gem.",
            "canonical_tags": ["Gem"],
            "user_tags": ["SDK", "Mobile"],
            "icon_path": "preview.png",
            "requirements": "",
            "documentation_url": "",
            "dependencies": ["Atom", "LmbrCentral"]
        }
        result = upgrade_to_latest(data, "gem")
        
        # Check schema
        assert result["$schemaVersion"] == "2.0.0"
        
        # Check nested gem structure
        assert "gem" in result
        assert result["gem"]["name"] == "org.o3de.gem.achievements"
        assert result["gem"]["display_name"] == "Achievements"
        assert result["gem"]["type"] == "code"
        
        # Check tags
        assert "tags" in result
        assert "Gem" in result["tags"]["canonical"]
        assert "SDK" in result["tags"]["user"]
        assert "Mobile" in result["tags"]["user"]
        
        # Check dependent gems
        assert "dependent" in result
        assert "org.o3de.gem.atom>=0.0.0" in result["dependent"]["gems"]
        assert "org.o3de.gem.lmbrcentral>=0.0.0" in result["dependent"]["gems"]
        
        # Check icon
        assert result["icon"]["relative_path"] == "preview.png"
    
    def test_atom_gem_with_children(self):
        """Should upgrade Atom gem with external_subdirectories."""
        data = {
            "gem_name": "Atom",
            "display_name": "Atom Renderer",
            "version": "1.0.0",
            "origin": "Open 3D Engine - o3de.org",
            "license": "Apache-2.0-Or-MIT",
            "external_subdirectories": [
                "Gems/Atom/Feature/Common",
                "Gems/Atom/RHI/Code"
            ]
        }
        result = upgrade_to_latest(data, "gem")
        
        # Check children.gems from external_subdirectories
        assert "children" in result
        assert any("Atom/Feature/Common" in p for p in result["children"]["gems"])
        assert any("Atom/RHI/Code" in p for p in result["children"]["gems"])


class TestRealisticProjectUpgrade:
    """Test project upgrade with realistic O3DE data."""
    
    def test_automated_testing_project(self):
        """Should upgrade realistic AutomatedTesting project from v0 to v2."""
        data = {
            "project_name": "AutomatedTesting",
            "product_name": "AutomatedTesting",
            "version": "1.1.0",
            "executable_name": "AutomatedTestingLauncher",
            "modules": [],
            "project_id": "{D816AFAE-4BB7-4FEF-88F4-E2B786DCF29D}",
            "display_name": "AutomatedTesting",
            "icon_path": "preview.png",
            "external_subdirectories": ["Gem"],
            "gem_names": ["Archive", "Atom", "Camera", "PhysX"]
        }
        result = upgrade_to_latest(data, "project")
        
        # Check schema
        assert result["$schemaVersion"] == "2.0.0"
        
        # Check nested project structure
        assert "project" in result
        assert result["project"]["name"] == "org.o3de.project.automatedtesting"
        assert result["project"]["version"] == "1.1.0"
        assert result["project"]["display_name"] == "AutomatedTesting"
        assert result["project"]["id"] == "{D816AFAE-4BB7-4FEF-88F4-E2B786DCF29D}"
        
        # Check preserved fields
        assert result["product_name"] == "AutomatedTesting"
        assert result["executable_name"] == "AutomatedTestingLauncher"
        
        # Check children.gems from external_subdirectories
        assert "children" in result
        assert "Gem/gem.json" in result["children"]["gems"]
        
        # Check dependent.gems from gem_names
        assert "dependent" in result
        assert len(result["dependent"]["gems"]) == 4
        assert "org.o3de.gem.archive>=0.0.0" in result["dependent"]["gems"]
        assert "org.o3de.gem.atom>=0.0.0" in result["dependent"]["gems"]
        
        # Check tags
        assert "Project" in result["tags"]["canonical"]
    
    def test_project_with_engine_reference(self):
        """Should convert engine reference to version specifier."""
        data = {
            "project_name": "MyGame",
            "engine": "o3de"
        }
        result = upgrade_to_latest(data, "project")
        
        assert result["engine"] == "org.o3de.engine.o3de>=1.0.0"
    
    def test_project_with_sdk_engine(self):
        """Should handle o3de-sdk engine reference."""
        data = {
            "project_name": "MyGame",
            "engine": "o3de-sdk"
        }
        result = upgrade_to_latest(data, "project")
        
        assert result["engine"] == "org.o3de.engine.o3de-sdk>=1.0.0"


class TestRealisticTemplateUpgrade:
    """Test template upgrade with realistic O3DE data."""
    
    def test_default_project_template(self):
        """Should upgrade DefaultProject template from v0 to v2."""
        data = {
            "template_name": "DefaultProject",
            "origin": "Open 3D Engine - o3de.org",
            "license": "Apache-2.0-Or-MIT",
            "license_url": "https://github.com/o3de/o3de/blob/development/LICENSE.txt",
            "display_name": "Default",
            "summary": "Default template for making new O3DE projects.",
            "canonical_tags": ["Template", "Project"],
            "user_tags": [],
            "icon_path": "preview.png",
            "copyFiles": [
                {"file": "CMakeLists.txt"},
                {"file": "project.json"},
                {"file": "Gem/Code/CMakeLists.txt"}
            ],
            "createDirectories": [
                {"dir": "Cache"},
                {"dir": "user"}
            ]
        }
        result = upgrade_to_latest(data, "template")
        
        # Check schema
        assert result["$schemaVersion"] == "2.0.0"
        
        # Check nested template structure
        assert "template" in result
        assert result["template"]["name"] == "org.o3de.template.defaultproject"
        assert result["template"]["display_name"] == "Default"
        
        # Check tags
        assert "Template" in result["tags"]["canonical"]
        assert "Project" in result["tags"]["canonical"]
        
        # Check copyFiles preserved
        assert "copyFiles" in result
        assert len(result["copyFiles"]) == 3
        
        # Check createDirectories preserved
        assert "createDirectories" in result
        assert len(result["createDirectories"]) == 2
        
        # Check licenses
        assert "licenses" in result
    
    def test_gem_template(self):
        """Should upgrade gem template from v0 to v2."""
        data = {
            "template_name": "DefaultGem",
            "display_name": "Default Gem",
            "summary": "Creates a default Gem with a basic CMake.",
            "canonical_tags": ["Template", "Gem"],
            "copyFiles": [{"file": "gem.json"}, {"file": "CMakeLists.txt"}]
        }
        result = upgrade_to_latest(data, "template")
        
        assert result["template"]["name"] == "org.o3de.template.defaultgem"
        assert "Gem" in result["tags"]["canonical"]
        assert "Template" in result["tags"]["canonical"]


class TestRealisticManifestUpgrade:
    """Test manifest upgrade with realistic O3DE data."""
    
    def test_user_manifest_upgrade(self):
        """Should upgrade realistic user manifest from v0 to v2."""
        data = {
            "o3de_manifest_name": "colin",
            "origin": "O3DE",
            "default_engines_folder": "C:/Users/colin/O3DE/Engines",
            "default_projects_folder": "C:/Users/colin/O3DE/Projects",
            "default_gems_folder": "C:/Users/colin/O3DE/Gems",
            "default_templates_folder": "C:/Users/colin/O3DE/Templates",
            "default_restricted_folder": "C:/Users/colin/O3DE/Restricteds",
            "default_third_party_folder": "C:/Users/colin/.o3de/3rdParty",
            "engines": ["F:/github/byrcolin/o3de"],
            "gems": ["C:/Users/colin/O3DE/Gems/marine.apmg/1.0.0"],
            "restricteds": [
                "C:/Users/colin/O3DE/Restricteds/Engines/org.o3de.restricted.o3de",
                "G:/overlo3de/apmg/o3de-jasper"
            ],
            "repos": [
                "https://canonical.o3de.org/repo.json"
            ]
        }
        result = upgrade_to_latest(data, "manifest")
        
        # Check schema
        assert result["$schemaVersion"] == "2.0.0"
        
        # Check nested manifest structure
        assert "o3de_manifest" in result
        assert result["o3de_manifest"]["name"] == "me.home.manifest.colin"
        
        # Check default paths
        assert "default" in result
        assert result["default"]["engines_path"] == "C:/Users/colin/O3DE/Engines"
        assert result["default"]["projects_path"] == "C:/Users/colin/O3DE/Projects"
        
        # Check local collections
        assert "local" in result
        assert len(result["local"]["engines"]) == 1
        assert len(result["local"]["gems"]) == 1
        assert len(result["local"]["restricteds"]) == 2
        
        # Check remote collections
        assert "remote" in result
        assert "https://canonical.o3de.org/repo.json" in result["remote"]["repos"]


class TestRealisticRestrictedUpgrade:
    """Test restricted upgrade with realistic O3DE data."""
    
    def test_jasper_restricted_upgrade(self):
        """Should upgrade Jasper restricted from v0 to v2."""
        data = {
            "restricted_name": "Jasper",
            "display_name": "Jasper Platform",
            "extends": "engine",
            "precedence": 100,
            "platform_maps": ["jasper:Jasper"],
            "platform_wart_maps": ["jasper:jasper"],
            "origin": "Access Point Media Group",
            "copyright_year": "2025",
            "copyright_text": "Copyright (C) 2025 Access Point Media Group"
        }
        result = upgrade_to_latest(data, "restricted")
        
        # Check schema
        assert result["$schemaVersion"] == "2.0.0"
        
        # Check nested restricted structure
        assert "restricted" in result
        assert result["restricted"]["name"] == "org.o3de.restricted.jasper"
        assert result["restricted"]["display_name"] == "Jasper Platform"
        assert result["restricted"]["copyright_year"] == "2025"
        
        # Check preserved fields
        assert result["extends"] == "engine"
        assert result["precedence"] == 100
        assert result["platform_maps"] == ["jasper:Jasper"]
        
        # Check platforms are empty for restricted
        assert result["platforms"] == []


class TestRealisticRepoUpgrade:
    """Test repo upgrade with realistic O3DE data."""
    
    def test_community_repo_upgrade(self):
        """Should upgrade community repo from v0 to v2."""
        data = {
            "repo_name": "o3de-community",
            "repo_uri": "https://canonical.o3de.org/repo.json",
            "origin": "Open 3D Engine Community",
            "origin_url": "https://www.o3de.org/community/",
            "summary": "Community repository for O3DE objects",
            "gems_data": [
                {"gem_name": "CommunityGem", "version": "1.0.0"}
            ],
            "projects_data": [],
            "templates_data": [],
            "repos": ["https://other.repo.org/repo.json"]
        }
        result = upgrade_to_latest(data, "repo")
        
        # Check schema
        assert result["$schemaVersion"] == "2.0.0"
        
        # Check nested repo structure
        assert "repo" in result
        assert result["repo"]["name"] == "org.o3de.repo.o3de-community"
        
        # Check origin
        assert "origin" in result
        assert result["origin"]["name"] == "Open 3D Engine Community"
        
        # Note: gems_data etc. not yet migrated to data structure
        # Check remote repos
        assert "remote" in result
        assert "https://other.repo.org/repo.json" in result["remote"]["repos"]

