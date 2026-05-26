# Tests for workspace schema, Pydantic model, file_owners, GUI tab, and migration
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""I-series tests: workspace schema + model + GUI tab."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner


# ── I1: Schema validation ──────────────────────────────────────────

class TestWorkspaceSchema:
    """Validate the canonical workspace JSON Schema."""

    def test_schema_file_exists(self):
        """o3de-workspace-2.0.0.json exists in canonical dir."""
        from o3de_pilot.core.schema import find_schema_directory
        schema_dir = find_schema_directory()
        if schema_dir is None:
            pytest.skip("canonical schema directory not found")
        assert (schema_dir / "o3de-workspace-2.0.0.json").exists()

    def test_schema_is_valid_json(self):
        from o3de_pilot.core.schema import find_schema_directory
        schema_dir = find_schema_directory()
        if schema_dir is None:
            pytest.skip("canonical schema directory not found")
        with open(schema_dir / "o3de-workspace-2.0.0.json") as f:
            data = json.load(f)
        assert data["title"] == "O3DE Workspace Schema 2.0.0"
        assert "workspace" in data["properties"]
        assert "file_owners" in data["properties"]
        assert "sources" in data["properties"]

    def test_validate_valid_workspace(self):
        """A well-formed workspace dict passes schema validation."""
        from o3de_pilot.core.schema import find_schema_directory
        schema_dir = find_schema_directory()
        if schema_dir is None:
            pytest.skip("canonical schema directory not found")
        try:
            import jsonschema
            import referencing
            import referencing.jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")

        with open(schema_dir / "o3de-workspace-2.0.0.json") as f:
            schema = json.load(f)
        resources = []
        for jf in schema_dir.glob("*.json"):
            try:
                with open(jf) as fp:
                    s = json.load(fp)
                if isinstance(s, dict):
                    sid = s.get("$id", f"./{jf.name}")
                    res = referencing.Resource.from_contents(
                        s, default_specification=referencing.jsonschema.DRAFT7
                    )
                    resources.append((sid, res))
            except Exception:
                continue
        registry = referencing.Registry().with_resources(resources)
        validator = jsonschema.Draft7Validator(schema, registry=registry)

        valid_data = {
            "$schema": "https://overlo3de.com/o3de-workspace-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "workspace": {"name": "test-build"},
            "created": "2026-05-25T12:00:00",
            "sources": ["/home/user/engine"],
        }
        errors = list(validator.iter_errors(valid_data))
        assert errors == []

    def test_validate_invalid_workspace_missing_workspace(self):
        """Missing required 'workspace' field is caught."""
        from o3de_pilot.core.schema import find_schema_directory
        schema_dir = find_schema_directory()
        if schema_dir is None:
            pytest.skip("canonical schema directory not found")
        try:
            import jsonschema
            import referencing
            import referencing.jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")

        with open(schema_dir / "o3de-workspace-2.0.0.json") as f:
            schema = json.load(f)
        resources = []
        for jf in schema_dir.glob("*.json"):
            try:
                with open(jf) as fp:
                    s = json.load(fp)
                if isinstance(s, dict):
                    sid = s.get("$id", f"./{jf.name}")
                    res = referencing.Resource.from_contents(
                        s, default_specification=referencing.jsonschema.DRAFT7
                    )
                    resources.append((sid, res))
            except Exception:
                continue
        registry = referencing.Registry().with_resources(resources)
        validator = jsonschema.Draft7Validator(schema, registry=registry)

        invalid_data = {
            "$schema": "https://overlo3de.com/o3de-workspace-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "created": "2026-05-25T12:00:00",
            "sources": [],
        }
        errors = list(validator.iter_errors(invalid_data))
        assert len(errors) > 0


# ── I1: Pydantic model ─────────────────────────────────────────────

class TestWorkspaceMeta:
    """WorkspaceMeta model round-trip and validation."""

    def test_round_trip(self):
        from o3de_pilot.core.models import WorkspaceMeta
        data = {
            "$schema": "https://overlo3de.com/o3de-workspace-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "workspace": {"name": "my-build", "version": "1.0.0"},
            "created": "2026-05-25T12:00:00",
            "root_object": "/home/user/engine",
            "root_type": "engine",
            "sources": ["/home/user/engine", "/home/user/project"],
            "overlays": ["/home/user/console-overlay"],
            "file_owners": {"engine.json": "org.o3de.engine.o3de"},
        }
        meta = WorkspaceMeta.model_validate(data)
        assert meta.workspace.name == "my-build"
        assert meta.workspace.version == "1.0.0"
        assert meta.root_type == "engine"
        assert len(meta.sources) == 2
        assert meta.file_owners["engine.json"] == "org.o3de.engine.o3de"

        # Round-trip
        dumped = meta.model_dump(by_alias=True, exclude_none=True)
        meta2 = WorkspaceMeta.model_validate(dumped)
        assert meta2.workspace.name == meta.workspace.name
        assert meta2.file_owners == meta.file_owners

    def test_minimal_valid(self):
        from o3de_pilot.core.models import WorkspaceMeta
        data = {
            "$schema": "https://overlo3de.com/o3de-workspace-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "workspace": {"name": "minimal"},
            "created": "2026-01-01T00:00:00",
        }
        meta = WorkspaceMeta.model_validate(data)
        assert meta.workspace.name == "minimal"
        assert meta.sources == []
        assert meta.file_owners == {}

    def test_missing_workspace_raises(self):
        from o3de_pilot.core.models import WorkspaceMeta
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            WorkspaceMeta.model_validate({
                "$schema": "x",
                "$schemaVersion": "2.0.0",
                "created": "2026-01-01",
            })

    def test_extra_fields_allowed(self):
        from o3de_pilot.core.models import WorkspaceMeta
        data = {
            "$schema": "x",
            "$schemaVersion": "2.0.0",
            "workspace": {"name": "test"},
            "created": "2026-01-01",
            "custom_field": "hello",
        }
        meta = WorkspaceMeta.model_validate(data)
        assert meta.workspace.name == "test"


# ── I2: Migration fallback ─────────────────────────────────────────

class TestWorkspaceMigration:
    """Test .workspace.json -> workspace.json fallback."""

    def test_find_new_name_preferred(self, tmp_path):
        from o3de_pilot.commands.workspace import _find_workspace_meta, WORKSPACE_META
        (tmp_path / WORKSPACE_META).write_text("{}")
        (tmp_path / ".workspace.json").write_text("{}")
        result = _find_workspace_meta(tmp_path)
        assert result.name == WORKSPACE_META

    def test_find_legacy_fallback(self, tmp_path):
        from o3de_pilot.commands.workspace import _find_workspace_meta
        (tmp_path / ".workspace.json").write_text("{}")
        result = _find_workspace_meta(tmp_path)
        assert result.name == ".workspace.json"

    def test_find_none_when_missing(self, tmp_path):
        from o3de_pilot.commands.workspace import _find_workspace_meta
        assert _find_workspace_meta(tmp_path) is None

    def test_read_legacy_format(self, tmp_path):
        from o3de_pilot.commands.workspace import _read_workspace_meta
        legacy = {"sources": ["/a", "/b"], "overlays": [], "name": "old-ws"}
        (tmp_path / ".workspace.json").write_text(json.dumps(legacy))
        meta = _read_workspace_meta(tmp_path)
        assert meta is not None
        assert meta.workspace.name == "old-ws"
        assert meta.sources == ["/a", "/b"]

    def test_write_creates_new_name(self, tmp_path):
        from o3de_pilot.commands.workspace import (
            _write_workspace_meta, _build_workspace_meta, WORKSPACE_META,
        )
        meta = _build_workspace_meta(
            name="test",
            root_path=Path("/engine"),
            root_type="engine",
            sources=["/engine"],
            overlays=[],
        )
        _write_workspace_meta(tmp_path, meta)
        assert (tmp_path / WORKSPACE_META).exists()
        data = json.loads((tmp_path / WORKSPACE_META).read_text())
        assert data["workspace"]["name"] == "test"
        assert "$schema" in data
        assert "$schemaVersion" in data


# ── I3: File ownership tracking ────────────────────────────────────

class TestFileOwnership:
    """Core Workspace class tracks file_owners."""

    def test_workspace_has_file_owners(self):
        from o3de_pilot.core.workspace import Workspace
        from o3de_pilot.core import ObjectType
        ws = Workspace(
            root_path=Path("/tmp/ws"),
            root_object_path=Path("/tmp/engine"),
            root_object_type=ObjectType.ENGINE,
        )
        assert hasattr(ws, "file_owners")
        assert ws.file_owners == {}

    def test_link_populates_owners(self, tmp_path):
        from o3de_pilot.core.workspace import Workspace
        from o3de_pilot.core import ObjectType

        # Create source files
        src = tmp_path / "src"
        src.mkdir()
        (src / "a.txt").write_text("hello")
        sub = src / "sub"
        sub.mkdir()
        (sub / "b.txt").write_text("world")

        ws_dir = tmp_path / "ws"
        ws = Workspace(
            root_path=ws_dir,
            root_object_path=src,
            root_object_type=ObjectType.ENGINE,
        )
        ws._link_object_files(src, 0, 10, owner_name="my-engine")

        assert "a.txt" in ws.file_owners
        assert ws.file_owners["a.txt"] == "my-engine"
        assert "sub/b.txt" in ws.file_owners
        assert ws.file_owners["sub/b.txt"] == "my-engine"

    def test_overlay_transfers_ownership(self, tmp_path):
        from o3de_pilot.core.workspace import Workspace
        from o3de_pilot.core import ObjectType

        # Create base + overlay
        base = tmp_path / "base"
        base.mkdir()
        (base / "config.txt").write_text("original")

        overlay = tmp_path / "overlay"
        overlay.mkdir()
        (overlay / "config.txt").write_text("patched")

        ws_dir = tmp_path / "ws"
        ws_dir.mkdir()

        ws = Workspace(
            root_path=ws_dir,
            root_object_path=base,
            root_object_type=ObjectType.ENGINE,
        )

        ws._link_object_files(base, 0, 10, owner_name="base-engine")
        assert ws.file_owners["config.txt"] == "base-engine"

        ws._apply_overlay(overlay, owner_name="console-overlay")
        assert ws.file_owners["config.txt"] == "console-overlay"


# ── I4: GUI Workspace Tab ──────────────────────────────────────────

class TestWorkspaceTab:
    """WorkspaceTab GUI construction and demo mode."""

    def test_construction(self, qtbot):
        from o3de_pilot.gui.workspace_tab import WorkspaceTab
        tab = WorkspaceTab(demo=True)
        qtbot.addWidget(tab)
        assert tab._ws_list.count() == 2  # demo has 2 workspaces

    def test_demo_tree_populated(self, qtbot):
        from o3de_pilot.gui.workspace_tab import WorkspaceTab
        tab = WorkspaceTab(demo=True)
        qtbot.addWidget(tab)
        # First item should be selected, tree populated
        assert tab._tree.topLevelItemCount() > 0

    def test_color_uniqueness(self, qtbot):
        from o3de_pilot.gui.workspace_tab import _assign_colors
        names = ["org.o3de.engine.o3de", "org.o3de.gem.atom", "com.example.project.demo"]
        colors = _assign_colors(names)
        assert len(colors) == 3
        hues = [c.hslHueF() for c in colors.values()]
        # All hues should be distinct
        assert len(set(round(h, 2) for h in hues)) == 3

    def test_assign_colors_empty(self):
        from o3de_pilot.gui.workspace_tab import _assign_colors
        assert _assign_colors([]) == {}

    def test_assign_colors_single(self):
        from o3de_pilot.gui.workspace_tab import _assign_colors
        colors = _assign_colors(["only-one"])
        assert len(colors) == 1

    def test_legend_built(self, qtbot):
        from o3de_pilot.gui.workspace_tab import WorkspaceTab
        tab = WorkspaceTab(demo=True)
        qtbot.addWidget(tab)
        # Legend should have widgets for each unique owner
        assert tab._legend_layout.count() > 0

    def test_workspace_tab_in_main_window(self, qtbot):
        from o3de_pilot.gui.main_window import MainWindow
        window = MainWindow()
        qtbot.addWidget(window)
        assert hasattr(window, "_workspace_tab")
        # Find the Workspaces tab
        found = False
        for i in range(window._tabs.count()):
            if window._tabs.tabText(i) == "Workspaces":
                found = True
                break
        assert found
