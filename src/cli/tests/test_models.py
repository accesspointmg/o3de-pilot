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
    Download,
    Binary,
    Release,
    Dependencies,
    Deprecated,
    Hooks,
    Engine,
    EngineHeader,
    Project,
    ProjectHeader,
    Gem,
    GemHeader,
    Template,
    TemplateHeader,
    Repo,
    RepoHeader,
    Overlay,
    OverlayHeader,
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


class TestDeprecated:
    """Test Deprecated model."""

    def test_required_message(self):
        dep = Deprecated(message="Use v2 instead")
        assert dep.message == "Use v2 instead"
        assert dep.replacement is None

    def test_with_replacement(self):
        dep = Deprecated(
            message="Critical bug",
            replacement="org.o3de.gem.mygem>=2.1.0"
        )
        assert dep.replacement == "org.o3de.gem.mygem>=2.1.0"


class TestHooks:
    """Test Hooks model."""

    def test_defaults(self):
        hooks = Hooks()
        assert hooks.post_install is None
        assert hooks.pre_build is None

    def test_with_scripts(self):
        hooks = Hooks(post_install="scripts/setup.py", pre_build="scripts/pre.py")
        assert hooks.post_install == "scripts/setup.py"
        assert hooks.pre_build == "scripts/pre.py"


class TestDownload:
    """Test Download model with SHA-256 fields."""

    def test_source_only(self):
        dl = Download(source="https://example.com/v1.zip")
        assert dl.source == "https://example.com/v1.zip"
        assert dl.lfs is None
        assert dl.source_sha256 is None
        assert dl.lfs_sha256 is None
        assert dl.relative_path is None

    def test_full(self):
        dl = Download(
            source="https://example.com/src.zip",
            lfs="https://example.com/lfs.zip",
            relative_path="Gems/MyGem",
            source_sha256="abcdef1234567890" * 4,
            lfs_sha256="1234567890abcdef" * 4,
        )
        assert dl.source_sha256 == "abcdef1234567890" * 4
        assert dl.lfs_sha256 == "1234567890abcdef" * 4
        assert dl.relative_path == "Gems/MyGem"


class TestBinary:
    """Test Binary model."""

    def test_required_fields(self):
        b = Binary(platform="Windows 11 AMD64", binary="https://example.com/bin.tar.gz")
        assert b.platform == "Windows 11 AMD64"
        assert b.binary == "https://example.com/bin.tar.gz"
        assert b.sha256 is None

    def test_with_sha256(self):
        b = Binary(
            platform="Ubuntu 24.04 AMD64",
            binary="https://example.com/bin.tar.gz",
            sha256="abc123" * 10 + "ab",
        )
        assert b.sha256 == "abc123" * 10 + "ab"


class TestRelease:
    """Test Release model (schema 2.0.0 uses 'name' not 'version')."""

    def test_name_required(self):
        r = Release(name="24.04")
        assert r.name == "24.04"
        assert r.downloads == []
        assert r.binaries == []
        assert r.source_controls == []

    def test_with_downloads_and_binaries(self):
        r = Release(
            name="Cherry",
            downloads=[Download(source="https://example.com/v1.zip")],
            binaries=[Binary(platform="Windows", binary="https://example.com/bin.zip")],
            source_controls=[SourceControl(uri="https://github.com/o3de/o3de.git", tag="v24.04")],
        )
        assert len(r.downloads) == 1
        assert len(r.binaries) == 1
        assert len(r.source_controls) == 1


class TestDependencies:
    """Test Dependencies model supports all 7 object types."""

    def test_defaults_empty(self):
        deps = Dependencies()
        assert deps.engines == []
        assert deps.projects == []
        assert deps.gems == []
        assert deps.templates == []
        assert deps.repos == []
        assert deps.overlays == []
        assert deps.manifests == []

    def test_all_types(self):
        deps = Dependencies(
            engines=["org.o3de.engine.core>=2.0.0"],
            projects=["org.o3de.project.sample"],
            gems=["org.o3de.gem.physx", "org.o3de.gem.atom"],
            templates=["org.o3de.template.basic"],
            repos=["org.o3de.repo.community"],
            overlays=["org.o3de.overlay.console"],
            manifests=["org.o3de.manifest.main"],
        )
        assert len(deps.engines) == 1
        assert len(deps.gems) == 2
        assert len(deps.manifests) == 1


class TestNewFieldsOnObjects:
    """Test that new schema 2.0.0 fields work on object models."""

    def test_gem_has_new_fields(self):
        gem = Gem(gem=GemHeader(name="org.o3de.gem.test"))
        assert gem.deprecated is None
        assert gem.hooks is None
        assert gem.optional_dependent.gems == []
        assert gem.peer_dependent.engines == []

    def test_gem_with_deprecated(self):
        gem = Gem(
            gem=GemHeader(name="org.o3de.gem.test"),
            deprecated=Deprecated(message="Use v2", replacement="org.o3de.gem.testv2"),
        )
        assert gem.deprecated.message == "Use v2"
        assert gem.deprecated.replacement == "org.o3de.gem.testv2"

    def test_gem_with_hooks(self):
        gem = Gem(
            gem=GemHeader(name="org.o3de.gem.test"),
            hooks=Hooks(post_install="setup.py"),
        )
        assert gem.hooks.post_install == "setup.py"

    def test_gem_with_optional_deps(self):
        gem = Gem(
            gem=GemHeader(name="org.o3de.gem.test"),
            optional_dependent=Dependencies(gems=["org.o3de.gem.optional>=1.0.0"]),
            peer_dependent=Dependencies(gems=["org.o3de.gem.peer>=2.0.0"]),
        )
        assert gem.optional_dependent.gems == ["org.o3de.gem.optional>=1.0.0"]
        assert gem.peer_dependent.gems == ["org.o3de.gem.peer>=2.0.0"]

    def test_engine_has_new_fields(self):
        eng = Engine(engine=EngineHeader(name="org.o3de.engine.core"))
        assert eng.deprecated is None
        assert eng.hooks is None
        assert eng.optional_dependent.gems == []
        assert eng.peer_dependent.gems == []

    def test_project_has_new_fields(self):
        proj = Project(project=ProjectHeader(name="org.o3de.project.test"))
        assert proj.deprecated is None
        assert proj.hooks is None
        assert proj.optional_dependent.gems == []

    def test_template_has_new_fields(self):
        tmpl = Template(template=TemplateHeader(name="org.o3de.template.test"))
        assert tmpl.deprecated is None
        assert tmpl.hooks is None
        assert tmpl.optional_dependent.gems == []

    def test_repo_has_new_fields(self):
        repo = Repo(repo=RepoHeader(name="org.o3de.repo.test"))
        assert repo.deprecated is None
        assert repo.hooks is None

    def test_overlay_has_new_fields(self):
        ov = Overlay(
            overlay=OverlayHeader(name="org.o3de.overlay.test"),
            extends="org.o3de.engine.core",
        )
        assert ov.deprecated is None
        assert ov.hooks is None
