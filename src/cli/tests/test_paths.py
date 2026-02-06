# O3DE Pilot - Path Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.paths module."""

import pytest
from pathlib import Path
from unittest.mock import patch
import tempfile
import os

from o3de_pilot.core.paths import (
    get_home_path,
    get_dot_o3de_path,
    get_o3de_path,
    get_cache_path,
    get_registry_path,
    get_logs_path,
    get_download_path,
    get_third_party_path,
    get_pilot_config_path,
    get_manifest_path,
    get_resolved_manifest_path,
    get_default_engines_path,
    get_default_projects_path,
    get_default_gems_path,
    get_default_templates_path,
    get_default_repos_path,
    get_default_overlays_path,
    get_default_layouts_path,
    get_default_path_for_type,
    ensure_directory,
    get_object_json_filename,
    get_versioned_object_json_filename,
    find_object_json,
)
from o3de_pilot.core.models import ObjectType


class TestBasePaths:
    """Test basic path functions."""
    
    def test_get_home_path(self):
        """Home path should be a valid directory."""
        home = get_home_path()
        assert isinstance(home, Path)
        assert home.exists()
    
    def test_get_dot_o3de_path(self):
        """Dot o3de path should be under home."""
        dot_o3de = get_dot_o3de_path()
        home = get_home_path()
        assert dot_o3de.parent == home
        assert dot_o3de.name == ".o3de"
    
    def test_get_o3de_path(self):
        """O3DE path should be under home."""
        o3de = get_o3de_path()
        home = get_home_path()
        assert o3de.parent == home
        assert o3de.name == "O3DE"


class TestSubdirectoryPaths:
    """Test subdirectory path functions."""
    
    def test_cache_path(self):
        """Cache path should be under .o3de."""
        cache = get_cache_path()
        assert cache.parent == get_dot_o3de_path()
        assert cache.name == "Cache"
    
    def test_registry_path(self):
        """Registry path should be under .o3de."""
        registry = get_registry_path()
        assert registry.parent == get_dot_o3de_path()
        assert registry.name == "Registry"
    
    def test_logs_path(self):
        """Logs path should be under .o3de."""
        logs = get_logs_path()
        assert logs.parent == get_dot_o3de_path()
        assert logs.name == "Logs"
    
    def test_download_path(self):
        """Download path should be under .o3de."""
        download = get_download_path()
        assert download.parent == get_dot_o3de_path()
        assert download.name == "Download"
    
    def test_third_party_path(self):
        """Third party path should be under .o3de."""
        third_party = get_third_party_path()
        assert third_party.parent == get_dot_o3de_path()
        assert third_party.name == "3rdParty"


class TestManifestPaths:
    """Test manifest path functions."""
    
    def test_manifest_path(self):
        """Manifest path should be under .o3de."""
        manifest = get_manifest_path()
        assert manifest.parent == get_dot_o3de_path()
        # Can be either versioned (2.0.0) or legacy file
        assert manifest.name in ("o3de_manifest.json", "o3de_manifest.2-0-0.json")
    
    def test_resolved_manifest_path(self):
        """Resolved manifest path should be under .o3de."""
        resolved = get_resolved_manifest_path()
        assert resolved.parent == get_dot_o3de_path()
        assert resolved.name == "resolved_o3de_manifest.json"


class TestDefaultObjectPaths:
    """Test default object storage paths."""
    
    def test_default_engines_path(self):
        """Engines path should be under O3DE."""
        engines = get_default_engines_path()
        assert engines.parent == get_o3de_path()
        assert engines.name == "Engines"
    
    def test_default_projects_path(self):
        """Projects path should be under O3DE."""
        projects = get_default_projects_path()
        assert projects.parent == get_o3de_path()
        assert projects.name == "Projects"
    
    def test_default_gems_path(self):
        """Gems path should be under O3DE."""
        gems = get_default_gems_path()
        assert gems.parent == get_o3de_path()
        assert gems.name == "Gems"
    
    def test_default_templates_path(self):
        """Templates path should be under O3DE."""
        templates = get_default_templates_path()
        assert templates.parent == get_o3de_path()
        assert templates.name == "Templates"
    
    def test_default_repos_path(self):
        """Repos path should be under O3DE."""
        repos = get_default_repos_path()
        assert repos.parent == get_o3de_path()
        assert repos.name == "Repos"
    
    def test_default_overlays_path(self):
        """Overlays path should be under O3DE."""
        overlays = get_default_overlays_path()
        assert overlays.parent == get_o3de_path()
        assert overlays.name == "Overlays"
    
    def test_default_layouts_path(self):
        """Layouts path should be under O3DE."""
        layouts = get_default_layouts_path()
        assert layouts.parent == get_o3de_path()
        assert layouts.name == "Layouts"


class TestGetDefaultPathForType:
    """Test get_default_path_for_type function."""
    
    def test_engine_type(self):
        """Engine type should map to Engines folder."""
        path = get_default_path_for_type(ObjectType.ENGINE)
        assert path == get_default_engines_path()
    
    def test_project_type(self):
        """Project type should map to Projects folder."""
        path = get_default_path_for_type(ObjectType.PROJECT)
        assert path == get_default_projects_path()
    
    def test_gem_type(self):
        """Gem type should map to Gems folder."""
        path = get_default_path_for_type(ObjectType.GEM)
        assert path == get_default_gems_path()
    
    def test_template_type(self):
        """Template type should map to Templates folder."""
        path = get_default_path_for_type(ObjectType.TEMPLATE)
        assert path == get_default_templates_path()
    
    def test_repo_type(self):
        """Repo type should map to Repos folder."""
        path = get_default_path_for_type(ObjectType.REPO)
        assert path == get_default_repos_path()
    
    def test_overlay_type(self):
        """Overlay type should map to Overlays folder."""
        path = get_default_path_for_type(ObjectType.OVERLAY)
        assert path == get_default_overlays_path()


class TestEnsureDirectory:
    """Test ensure_directory function."""
    
    def test_creates_directory(self):
        """Should create directory that doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_dir = Path(tmpdir) / "new" / "nested" / "dir"
            assert not new_dir.exists()
            
            result = ensure_directory(new_dir)
            
            assert result == new_dir
            assert new_dir.exists()
            assert new_dir.is_dir()
    
    def test_existing_directory(self):
        """Should handle existing directory gracefully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            existing = Path(tmpdir)
            assert existing.exists()
            
            result = ensure_directory(existing)
            
            assert result == existing
            assert existing.exists()


class TestObjectJsonFilenames:
    """Test object JSON filename functions."""
    
    def test_get_object_json_filename(self):
        """Should return correct JSON filename."""
        assert get_object_json_filename("engine") == "engine.json"
        assert get_object_json_filename("project") == "project.json"
        assert get_object_json_filename("gem") == "gem.json"
        assert get_object_json_filename("template") == "template.json"
        assert get_object_json_filename("repo") == "repo.json"
        assert get_object_json_filename("overlay") == "overlay.json"
    
    def test_get_versioned_object_json_filename(self):
        """Should return versioned JSON filename with dashes."""
        assert get_versioned_object_json_filename("engine") == "engine.2-0-0.json"
        assert get_versioned_object_json_filename("gem", "2.0.0") == "gem.2-0-0.json"
        assert get_versioned_object_json_filename("project", "1.0.0") == "project.1-0-0.json"
        assert get_versioned_object_json_filename("engine", "3.1.2") == "engine.3-1-2.json"


class TestFindObjectJson:
    """Test find_object_json function."""
    
    def test_finds_versioned_file_first(self):
        """Should prefer versioned file over legacy file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Create both versioned and legacy files
            (path / "gem.2-0-0.json").write_text("{}")
            (path / "gem.json").write_text("{}")
            
            json_path, is_versioned = find_object_json(path, "gem")
            
            assert json_path.name == "gem.2-0-0.json"
            assert is_versioned is True
    
    def test_falls_back_to_legacy(self):
        """Should use legacy file when versioned doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            # Only create legacy file
            (path / "gem.json").write_text("{}")
            
            json_path, is_versioned = find_object_json(path, "gem")
            
            assert json_path.name == "gem.json"
            assert is_versioned is False
    
    def test_raises_when_not_found(self):
        """Should raise FileNotFoundError when no JSON exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            with pytest.raises(FileNotFoundError) as exc:
                find_object_json(path, "gem")
            
            assert "gem.json" in str(exc.value)
    
    def test_different_object_types(self):
        """Should work for different object types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            
            (path / "engine.2-0-0.json").write_text("{}")
            json_path, is_versioned = find_object_json(path, "engine")
            assert json_path.name == "engine.2-0-0.json"
            assert is_versioned is True
            
            path2 = Path(tmpdir) / "project_dir"
            path2.mkdir()
            (path2 / "project.json").write_text("{}")
            json_path2, is_versioned2 = find_object_json(path2, "project")
            assert json_path2.name == "project.json"
            assert is_versioned2 is False
