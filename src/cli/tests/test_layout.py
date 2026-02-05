# O3DE Pilot - Layout Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.layout module."""

import pytest
import tempfile
from pathlib import Path

from o3de_pilot.core.layout import (
    Layout,
    LayoutError,
)
from o3de_pilot.core.models import ObjectType


class TestLayoutInit:
    """Test Layout initialization."""
    
    def test_creation(self):
        """Should create Layout with required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert layout.root_path == Path(tmpdir) / "layout"
            assert layout.root_object_path == Path(tmpdir) / "engine"
            assert layout.root_object_type == ObjectType.ENGINE
    
    def test_empty_resolved_objects(self):
        """Should start with empty resolved objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert layout.resolved_objects == {}
    
    def test_empty_overlays(self):
        """Should start with empty overlays list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert layout.overlays == []
    
    def test_empty_linked_files(self):
        """Should start with empty linked files dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert layout.linked_files == {}
    
    def test_default_exclude_patterns(self):
        """Should have sensible default exclude patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert ".git" in layout.exclude_patterns
            assert "__pycache__" in layout.exclude_patterns


class TestLayoutAddResolvedObject:
    """Test adding resolved objects to layout."""
    
    def test_add_single_object(self):
        """Should add a single resolved object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            gem_path = Path(tmpdir) / "Gems" / "TestGem"
            layout.add_resolved_object("org.test.gem.test", gem_path)
            
            assert "org.test.gem.test" in layout.resolved_objects
            assert layout.resolved_objects["org.test.gem.test"] == gem_path
    
    def test_add_multiple_objects(self):
        """Should add multiple resolved objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            layout.add_resolved_object("gem1", Path(tmpdir) / "gem1")
            layout.add_resolved_object("gem2", Path(tmpdir) / "gem2")
            layout.add_resolved_object("gem3", Path(tmpdir) / "gem3")
            
            assert len(layout.resolved_objects) == 3


class TestLayoutAddOverlay:
    """Test adding overlays to layout."""
    
    def test_add_single_overlay(self):
        """Should add a single overlay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            overlay_path = Path(tmpdir) / "overlay"
            layout.add_overlay(overlay_path, precedence=0)
            
            assert len(layout.overlays) == 1
            assert layout.overlays[0][0] == overlay_path
            assert layout.overlays[0][1] == 0
    
    def test_overlays_sorted_by_precedence(self):
        """Overlays should be sorted by precedence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            # Add overlays out of order
            layout.add_overlay(Path(tmpdir) / "high", precedence=100)
            layout.add_overlay(Path(tmpdir) / "low", precedence=10)
            layout.add_overlay(Path(tmpdir) / "mid", precedence=50)
            
            # Should be sorted by precedence
            precedences = [o[1] for o in layout.overlays]
            assert precedences == [10, 50, 100]


class TestLayoutShouldExclude:
    """Test file exclusion patterns."""
    
    def test_exclude_git_directory(self):
        """Should exclude .git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            assert layout.should_exclude(Path(".git"))
    
    def test_exclude_pycache(self):
        """Should exclude __pycache__ directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            assert layout.should_exclude(Path("__pycache__"))
    
    def test_exclude_pyc_files(self):
        """Should exclude .pyc files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            assert layout.should_exclude(Path("module.pyc"))
    
    def test_include_normal_files(self):
        """Should not exclude regular source files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout = Layout(
                root_path=Path(tmpdir) / "layout",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            assert not layout.should_exclude(Path("main.cpp"))
            assert not layout.should_exclude(Path("script.py"))
            assert not layout.should_exclude(Path("config.json"))
            assert not layout.should_exclude(Path("README.md"))


class TestLayoutError:
    """Test LayoutError exception."""
    
    def test_is_exception(self):
        """LayoutError should be an Exception."""
        error = LayoutError("layout error")
        assert isinstance(error, Exception)
        assert str(error) == "layout error"


class TestLayoutCreate:
    """Test Layout creation."""
    
    def test_create_raises_if_exists(self):
        """Should raise if layout path already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout_path = Path(tmpdir) / "layout"
            layout_path.mkdir()
            
            layout = Layout(
                root_path=layout_path,
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            with pytest.raises(LayoutError) as exc:
                layout.create()
            
            assert "already exists" in str(exc.value)
    
    def test_create_with_clean_removes_existing(self):
        """Should remove existing layout when clean=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            layout_path = Path(tmpdir) / "layout"
            layout_path.mkdir()
            (layout_path / "old_file.txt").write_text("old content")
            
            engine_path = Path(tmpdir) / "engine"
            engine_path.mkdir()
            
            layout = Layout(
                root_path=layout_path,
                root_object_path=engine_path,
                root_object_type=ObjectType.ENGINE
            )
            
            # Should succeed with clean=True
            layout.create(clean=True)
            
            assert layout_path.exists()
            assert not (layout_path / "old_file.txt").exists()
