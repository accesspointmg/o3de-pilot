# O3DE Pilot - Models Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.models module."""

import pytest

from o3de_pilot.core.models import (
    ObjectType,
    GemType,
    EngineType,
    Origin,
    License,
    Icon,
    Documentation,
    SourceControl,
    OBJECT_NAME_PATTERN,
    VERSION_PATTERN,
    get_object_type,
    get_object_name,
    get_object_version,
)


class TestPatterns:
    """Test regex patterns."""
    
    def test_object_name_pattern_valid(self):
        """Should match valid reverse domain names."""
        valid_names = [
            "org.o3de.gem.myname",
            "com.example.gem.feature",
            "io.github.user.template",
            "net.company.project.game",
            "dev.studio.engine.fork",
        ]
        for name in valid_names:
            assert OBJECT_NAME_PATTERN.match(name), f"Should match: {name}"
    
    def test_object_name_pattern_invalid(self):
        """Should reject invalid names."""
        invalid_names = [
            "gem",                    # Too short
            "myname",                 # No dots
            "Org.O3DE.gem",          # Uppercase
            "org",                    # Too few parts
            "org.gem",                # Only 2 parts
            "123.invalid.name",       # Starts with number
        ]
        for name in invalid_names:
            assert not OBJECT_NAME_PATTERN.match(name), f"Should not match: {name}"
    
    def test_version_pattern_valid(self):
        """Should match valid semver versions."""
        valid_versions = [
            "0.0.0",
            "1.0.0",
            "2.1.3",
            "10.20.30",
            "123.456.789",
        ]
        for version in valid_versions:
            assert VERSION_PATTERN.match(version), f"Should match: {version}"
    
    def test_version_pattern_invalid(self):
        """Should reject invalid versions."""
        invalid_versions = [
            "1",                     # Missing parts
            "1.0",                   # Missing patch
            "v1.0.0",               # Has prefix
            "1.0.0-beta",           # Has suffix
            "1.0.0.0",              # Extra part
            "a.b.c",                # Non-numeric
        ]
        for version in invalid_versions:
            assert not VERSION_PATTERN.match(version), f"Should not match: {version}"


class TestObjectType:
    """Test ObjectType enum."""
    
    def test_enum_values(self):
        """Should have correct string values."""
        assert ObjectType.ENGINE.value == "engine"
        assert ObjectType.PROJECT.value == "project"
        assert ObjectType.GEM.value == "gem"
        assert ObjectType.TEMPLATE.value == "template"
        assert ObjectType.REPO.value == "repo"
        assert ObjectType.OVERLAY.value == "overlay"
        assert ObjectType.MANIFEST.value == "manifest"


class TestGemType:
    """Test GemType enum."""
    
    def test_enum_values(self):
        """Should have correct string values."""
        assert GemType.CODE.value == "code"
        assert GemType.ASSET.value == "asset"


class TestEngineType:
    """Test EngineType enum."""
    
    def test_enum_values(self):
        """Should have correct string values."""
        assert EngineType.FULL.value == "full"
        assert EngineType.SLIM.value == "slim"


class TestOrigin:
    """Test Origin model."""
    
    def test_default_values(self):
        """Should have sensible defaults."""
        origin = Origin()
        assert origin.name == ""
        assert origin.url is None
        assert origin.email is None
    
    def test_full_values(self):
        """Should accept all fields."""
        origin = Origin(
            name="O3DE Foundation",
            url="https://o3de.org",
            email="info@o3de.org"
        )
        assert origin.name == "O3DE Foundation"
        assert origin.url == "https://o3de.org"
        assert origin.email == "info@o3de.org"


class TestLicense:
    """Test License model."""
    
    def test_required_name(self):
        """Should require license name."""
        license_info = License(name="Apache-2.0")
        assert license_info.name == "Apache-2.0"
        assert license_info.url is None
    
    def test_with_url(self):
        """Should accept URL."""
        license_info = License(
            name="MIT",
            url="https://opensource.org/licenses/MIT"
        )
        assert license_info.name == "MIT"
        assert license_info.url == "https://opensource.org/licenses/MIT"


class TestGetObjectType:
    """Test get_object_type function."""
    
    def test_schema_2_engine(self):
        """Should detect engine from Schema 2.0.0 format."""
        data = {
            "$schema": "https://overlo3de.com/o3de-engine-2.0.0.json",
            "engine": {"name": "org.o3de.engine.core", "version": "2.0.0"}
        }
        assert get_object_type(data) == ObjectType.ENGINE
    
    def test_schema_2_project(self):
        """Should detect project from Schema 2.0.0 format."""
        data = {
            "$schema": "https://overlo3de.com/o3de-project-2.0.0.json",
            "project": {"name": "org.o3de.project.test", "version": "1.0.0"}
        }
        assert get_object_type(data) == ObjectType.PROJECT
    
    def test_schema_2_gem(self):
        """Should detect gem from Schema 2.0.0 format."""
        data = {
            "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
            "gem": {"name": "org.o3de.gem.atoms", "version": "1.0.0"}
        }
        assert get_object_type(data) == ObjectType.GEM
    
    def test_schema_2_template(self):
        """Should detect template from Schema 2.0.0 format."""
        data = {
            "$schema": "https://overlo3de.com/o3de-template-2.0.0.json",
            "template": {"name": "org.o3de.template.project", "version": "1.0.0"}
        }
        assert get_object_type(data) == ObjectType.TEMPLATE
    
    def test_schema_2_repo(self):
        """Should detect repo from Schema 2.0.0 format."""
        data = {
            "$schema": "https://overlo3de.com/o3de-repo-2.0.0.json",
            "repo": {"name": "org.o3de.repo.community", "version": "1.0.0"}
        }
        assert get_object_type(data) == ObjectType.REPO
    
    def test_schema_2_manifest(self):
        """Should detect manifest from Schema 2.0.0 format."""
        data = {
            "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
            "o3de_manifest": {"name": "me.home.user.manifest"}
        }
        assert get_object_type(data) == ObjectType.MANIFEST
    
    def test_legacy_engine(self):
        """Should detect engine from legacy format."""
        data = {"engine_name": "o3de", "version": "1.0.0"}
        assert get_object_type(data) == ObjectType.ENGINE
    
    def test_legacy_project(self):
        """Should detect project from legacy format."""
        data = {"project_name": "MyGame", "version": "1.0.0"}
        assert get_object_type(data) == ObjectType.PROJECT
    
    def test_legacy_gem(self):
        """Should detect gem from legacy format."""
        data = {"gem_name": "MyGem", "version": "1.0.0"}
        assert get_object_type(data) == ObjectType.GEM
    
    def test_legacy_template(self):
        """Should detect template from legacy format."""
        data = {"template_name": "DefaultProject", "version": "1.0.0"}
        assert get_object_type(data) == ObjectType.TEMPLATE
    
    def test_legacy_repo_by_name(self):
        """Should detect repo from legacy format by name."""
        data = {"repo_name": "community", "repo_uri": "https://example.com"}
        assert get_object_type(data) == ObjectType.REPO
    
    def test_unknown_raises(self):
        """Should raise for unrecognizable dict."""
        data = {"unknown_field": "value"}
        with pytest.raises(ValueError) as exc:
            get_object_type(data)
        assert "Cannot determine object type" in str(exc.value)


class TestGetObjectName:
    """Test get_object_name function."""
    
    def test_schema_2_formats(self):
        """Should extract name from Schema 2.0.0 format."""
        test_cases = [
            ({"engine": {"name": "org.o3de.engine.core"}}, "org.o3de.engine.core"),
            ({"project": {"name": "org.o3de.project.test"}}, "org.o3de.project.test"),
            ({"gem": {"name": "org.o3de.gem.atoms"}}, "org.o3de.gem.atoms"),
            ({"template": {"name": "org.o3de.template.project"}}, "org.o3de.template.project"),
            ({"repo": {"name": "org.o3de.repo.community"}}, "org.o3de.repo.community"),
        ]
        for data, expected in test_cases:
            assert get_object_name(data) == expected
    
    def test_legacy_formats(self):
        """Should extract name from legacy format."""
        test_cases = [
            ({"engine_name": "o3de"}, "o3de"),
            ({"project_name": "MyGame"}, "MyGame"),
            ({"gem_name": "MyGem"}, "MyGem"),
            ({"template_name": "DefaultProject"}, "DefaultProject"),
            ({"repo_name": "community"}, "community"),
        ]
        for data, expected in test_cases:
            assert get_object_name(data) == expected
    
    def test_missing_name_returns_empty(self):
        """Should return empty string when name not found."""
        data = {"engine": {}}
        assert get_object_name(data) == ""


class TestGetObjectVersion:
    """Test get_object_version function."""
    
    def test_schema_2_formats(self):
        """Should extract version from Schema 2.0.0 format."""
        test_cases = [
            ({"engine": {"name": "test", "version": "2.0.0"}}, "2.0.0"),
            ({"project": {"name": "test", "version": "1.5.0"}}, "1.5.0"),
            ({"gem": {"name": "test", "version": "3.2.1"}}, "3.2.1"),
        ]
        for data, expected in test_cases:
            assert get_object_version(data) == expected
    
    def test_legacy_version_at_top(self):
        """Should extract version from legacy top-level."""
        data = {"engine_name": "o3de", "version": "1.0.0"}
        assert get_object_version(data) == "1.0.0"
    
    def test_origin_based_version(self):
        """Should extract version from origin field."""
        data = {"origin": {"version": "1.2.3"}}
        assert get_object_version(data) == "1.2.3"
    
    def test_missing_version_returns_default(self):
        """Should return 0.0.0 when version not found."""
        data = {"engine": {"name": "test"}}
        assert get_object_version(data) == "0.0.0"
