# O3DE Pilot - Workspace Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.workspace module."""

import pytest
import tempfile
from pathlib import Path

from o3de_pilot.core.workspace import (
    Workspace,
    WorkspaceError,
)
from o3de_pilot.core.models import ObjectType


class TestWorkspaceInit:
    """Test Workspace initialization."""
    
    def test_creation(self):
        """Should create Workspace with required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert ws.root_path == Path(tmpdir) / "workspace"
            assert ws.root_object_path == Path(tmpdir) / "engine"
            assert ws.root_object_type == ObjectType.ENGINE
    
    def test_empty_resolved_objects(self):
        """Should start with empty resolved objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert ws.resolved_objects == {}
    
    def test_empty_overlays(self):
        """Should start with empty overlays list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert ws.overlays == []
    
    def test_empty_linked_files(self):
        """Should start with empty linked files dict."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert ws.linked_files == {}
    
    def test_default_exclude_patterns(self):
        """Should have sensible default exclude patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            assert ".git" in ws.exclude_patterns
            assert "__pycache__" in ws.exclude_patterns


class TestWorkspaceAddResolvedObject:
    """Test adding resolved objects to workspace."""
    
    def test_add_single_object(self):
        """Should add a single resolved object."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            gem_path = Path(tmpdir) / "Gems" / "TestGem"
            ws.add_resolved_object("org.test.gem.test", gem_path)
            
            assert "org.test.gem.test" in ws.resolved_objects
            assert ws.resolved_objects["org.test.gem.test"] == gem_path
    
    def test_add_multiple_objects(self):
        """Should add multiple resolved objects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            ws.add_resolved_object("gem1", Path(tmpdir) / "gem1")
            ws.add_resolved_object("gem2", Path(tmpdir) / "gem2")
            ws.add_resolved_object("gem3", Path(tmpdir) / "gem3")
            
            assert len(ws.resolved_objects) == 3


class TestWorkspaceAddOverlay:
    """Test adding overlays to workspace."""
    
    def test_add_single_overlay(self):
        """Should add a single overlay."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            overlay_path = Path(tmpdir) / "overlay"
            ws.add_overlay(overlay_path, precedence=0)
            
            assert len(ws.overlays) == 1
            assert ws.overlays[0][0] == overlay_path
            assert ws.overlays[0][1] == 0
    
    def test_overlays_sorted_by_precedence(self):
        """Overlays should be sorted by precedence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            # Add overlays out of order
            ws.add_overlay(Path(tmpdir) / "high", precedence=100)
            ws.add_overlay(Path(tmpdir) / "low", precedence=10)
            ws.add_overlay(Path(tmpdir) / "mid", precedence=50)
            
            # Should be sorted by precedence
            precedences = [o[1] for o in ws.overlays]
            assert precedences == [10, 50, 100]


class TestWorkspaceShouldExclude:
    """Test file exclusion patterns."""
    
    def test_exclude_git_directory(self):
        """Should exclude .git directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            assert ws.should_exclude(Path(".git"))
    
    def test_exclude_pycache(self):
        """Should exclude __pycache__ directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            assert ws.should_exclude(Path("__pycache__"))
    
    def test_exclude_pyc_files(self):
        """Should exclude .pyc files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            assert ws.should_exclude(Path("module.pyc"))
    
    def test_include_normal_files(self):
        """Should not exclude regular source files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Workspace(
                root_path=Path(tmpdir) / "workspace",
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            assert not ws.should_exclude(Path("main.cpp"))
            assert not ws.should_exclude(Path("script.py"))
            assert not ws.should_exclude(Path("config.json"))
            assert not ws.should_exclude(Path("README.md"))


class TestWorkspaceError:
    """Test WorkspaceError exception."""
    
    def test_is_exception(self):
        """WorkspaceError should be an Exception."""
        error = WorkspaceError("workspace error")
        assert isinstance(error, Exception)
        assert str(error) == "workspace error"


class TestWorkspaceCreate:
    """Test Workspace creation."""
    
    def test_create_raises_if_exists(self):
        """Should raise if workspace path already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws_path = Path(tmpdir) / "workspace"
            ws_path.mkdir()
            
            ws = Workspace(
                root_path=ws_path,
                root_object_path=Path(tmpdir) / "engine",
                root_object_type=ObjectType.ENGINE
            )
            
            with pytest.raises(WorkspaceError) as exc:
                ws.create()
            
            assert "already exists" in str(exc.value)
    
    def test_create_with_clean_removes_existing(self):
        """Should remove existing workspace when clean=True."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ws_path = Path(tmpdir) / "workspace"
            ws_path.mkdir()
            (ws_path / "old_file.txt").write_text("old content")
            
            engine_path = Path(tmpdir) / "engine"
            engine_path.mkdir()
            
            ws = Workspace(
                root_path=ws_path,
                root_object_path=engine_path,
                root_object_type=ObjectType.ENGINE
            )
            
            # Should succeed with clean=True
            ws.create(clean=True)
            
            assert ws_path.exists()
            assert not (ws_path / "old_file.txt").exists()
