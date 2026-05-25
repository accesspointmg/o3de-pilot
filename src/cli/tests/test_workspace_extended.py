# O3DE Pilot - Extended Workspace Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Extended tests for o3de_pilot.core.workspace module — covers create, link, overlay, update, stats."""

import pytest
from pathlib import Path

from o3de_pilot.core.workspace import (
    Workspace,
    WorkspaceError,
    LayoutError,
    create_workspace,
)
from o3de_pilot.core.models import ObjectType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(tmp_path, **kw):
    engine = tmp_path / "engine"
    engine.mkdir()
    return Workspace(
        root_path=kw.get("root_path", tmp_path / "ws"),
        root_object_path=kw.get("root_object_path", engine),
        root_object_type=kw.get("root_object_type", ObjectType.ENGINE),
    )


def _write(path: Path, text: str = "content"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


# ---------------------------------------------------------------------------
# TestLayoutErrorAlias
# ---------------------------------------------------------------------------

class TestLayoutErrorAlias:
    def test_alias_is_workspace_error(self):
        assert LayoutError is WorkspaceError


# ---------------------------------------------------------------------------
# TestShouldExcludeAdvanced
# ---------------------------------------------------------------------------

class TestShouldExcludeAdvanced:
    """More exclusion pattern scenarios."""

    def test_exclude_build_subdir(self, tmp_path):
        ws = _make_ws(tmp_path)
        assert ws.should_exclude(Path("build/Release/game.exe"))

    def test_exclude_cache_subdir(self, tmp_path):
        ws = _make_ws(tmp_path)
        assert ws.should_exclude(Path("Cache/products/mesh.azmodel"))

    def test_exclude_log_files(self, tmp_path):
        ws = _make_ws(tmp_path)
        assert ws.should_exclude(Path("output.log"))

    def test_exclude_nested_pycache(self, tmp_path):
        ws = _make_ws(tmp_path)
        assert ws.should_exclude(Path("src/__pycache__"))

    def test_include_cmake(self, tmp_path):
        ws = _make_ws(tmp_path)
        assert not ws.should_exclude(Path("CMakeLists.txt"))

    def test_include_source(self, tmp_path):
        ws = _make_ws(tmp_path)
        assert not ws.should_exclude(Path("Code/Source/main.cpp"))


# ---------------------------------------------------------------------------
# TestWorkspaceCreate
# ---------------------------------------------------------------------------

class TestWorkspaceCreateExtended:
    """Test workspace creation and linking."""

    def test_create_links_files(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "engine.json", '{"engine": {"name": "test"}}')
        _write(engine / "Code" / "main.cpp", "int main() {}")

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)
        ws.create()

        assert (tmp_path / "ws").exists()
        assert len(ws.linked_files) >= 1

    def test_create_with_progress(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "file.txt", "data")

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)

        calls = []
        ws.create(progress_callback=lambda msg, cur, tot: calls.append(msg))
        assert any("Complete" in c for c in calls)

    def test_create_excludes_git(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "src.cpp", "code")
        _write(engine / ".git" / "config", "[core]")

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)
        ws.create()

        linked_names = {p.name for p in ws.linked_files.keys()}
        assert "config" not in linked_names  # .git/config excluded
        assert "src.cpp" in linked_names


# ---------------------------------------------------------------------------
# TestOverlayApplication
# ---------------------------------------------------------------------------

class TestOverlayApplication:
    """Test overlay application."""

    def test_overlay_replaces_base_file(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "data.txt", "base content")

        overlay = tmp_path / "overlay"
        overlay.mkdir()
        _write(overlay / "data.txt", "overlay content")

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)
        ws.add_overlay(overlay, precedence=0)
        ws.create()

        # The link should point to overlay file
        target = tmp_path / "ws" / "data.txt"
        assert target.exists()

    def test_overlay_adds_new_file(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "base.txt", "base")

        overlay = tmp_path / "overlay"
        overlay.mkdir()
        _write(overlay / "extra.txt", "extra")

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)
        ws.add_overlay(overlay, precedence=0)
        ws.create()

        assert (tmp_path / "ws" / "extra.txt").exists()

    def test_overlay_json_skipped(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "file.txt", "data")

        overlay = tmp_path / "overlay"
        overlay.mkdir()
        _write(overlay / "overlay.json", '{"overlay": {}}')
        _write(overlay / "real.txt", "real")

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)
        ws.add_overlay(overlay)
        ws.create()

        assert not (tmp_path / "ws" / "overlay.json").exists()

    def test_missing_overlay_warning(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "file.txt", "data")

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)
        ws.add_overlay(tmp_path / "nonexistent", precedence=0)
        ws.create()
        # Should not raise — just warns


# ---------------------------------------------------------------------------
# TestWorkspaceUpdate
# ---------------------------------------------------------------------------

class TestWorkspaceUpdate:
    """Test update method."""

    def test_update_on_nonexistent_raises(self, tmp_path):
        ws = _make_ws(tmp_path)
        with pytest.raises(WorkspaceError, match="does not exist"):
            ws.update()

    def test_update_reapplies_overlay(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "file.txt", "base")

        overlay = tmp_path / "overlay"
        overlay.mkdir()

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)
        ws.add_overlay(overlay)
        ws.create()

        # Now add a file to overlay and update
        _write(overlay / "new.txt", "added")
        ws.update()

        assert (tmp_path / "ws" / "new.txt").exists()


# ---------------------------------------------------------------------------
# TestWorkspaceGetStats
# ---------------------------------------------------------------------------

class TestWorkspaceGetStats:
    """Test get_stats method."""

    def test_stats_structure(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "a.txt", "a")

        ws = Workspace(tmp_path / "ws", engine, ObjectType.ENGINE)
        ws.add_resolved_object("root", engine)
        ws.create()

        stats = ws.get_stats()
        assert "root_path" in stats
        assert "total_files" in stats
        assert "resolved_objects" in stats
        assert "overlays" in stats
        assert stats["total_files"] == 1
        assert stats["resolved_objects"] == 1
        assert stats["overlays"] == 0


# ---------------------------------------------------------------------------
# TestCreateWorkspaceConvenience
# ---------------------------------------------------------------------------

class TestCreateWorkspaceConvenience:
    """Test create_workspace() convenience function."""

    def test_engine_root(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "engine.json", '{"engine": {"name": "test"}}')
        _write(engine / "code.cpp", "code")

        ws = create_workspace(
            target_path=tmp_path / "ws",
            root_object_path=engine,
            resolved_objects={},
        )
        assert (tmp_path / "ws").exists()
        assert ws.root_object_type == ObjectType.ENGINE

    def test_project_root(self, tmp_path):
        proj = tmp_path / "project"
        proj.mkdir()
        _write(proj / "project.json", '{"project": {"name": "test"}}')
        _write(proj / "code.cpp", "code")

        ws = create_workspace(
            target_path=tmp_path / "ws",
            root_object_path=proj,
            resolved_objects={},
        )
        assert ws.root_object_type == ObjectType.PROJECT

    def test_unknown_root_raises(self, tmp_path):
        unknown = tmp_path / "unknown"
        unknown.mkdir()

        with pytest.raises(WorkspaceError, match="Cannot determine root object type"):
            create_workspace(
                target_path=tmp_path / "ws",
                root_object_path=unknown,
                resolved_objects={},
            )

    def test_with_overlays(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "engine.json", '{"engine": {"name": "test"}}')

        overlay = tmp_path / "ov"
        overlay.mkdir()
        _write(overlay / "patch.txt", "patch")

        ws = create_workspace(
            target_path=tmp_path / "ws",
            root_object_path=engine,
            resolved_objects={},
            overlays=[(overlay, 0)],
        )
        assert (tmp_path / "ws" / "patch.txt").exists()

    def test_with_resolved_objects(self, tmp_path):
        engine = tmp_path / "engine"
        engine.mkdir()
        _write(engine / "engine.json", '{"engine": {"name": "test"}}')

        gem = tmp_path / "gem"
        gem.mkdir()
        _write(gem / "gem.json", '{"gem": {"name": "mygem"}}')

        ws = create_workspace(
            target_path=tmp_path / "ws",
            root_object_path=engine,
            resolved_objects={"mygem": gem},
        )
        assert ws.resolved_objects.get("mygem") is not None
