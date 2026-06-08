# O3DE Pilot - Workspace Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for workspace CLI commands."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from tests.conftest import _write_json


def _manifest(tmp_path):
    mp = tmp_path / "o3de_manifest.2-0-0.json"
    _write_json(mp, {
        "$schemaVersion": "2.0.0",
        "o3de_manifest": {"name": "test"},
        "local": {"engines": [], "projects": [], "gems": [],
                  "templates": [], "repos": [], "overlays": []},
        "remotes": [],
    })
    return mp


def _engine(tmp_path, name="org.test.engine"):
    edir = tmp_path / "engine"
    edir.mkdir(exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        "engine": {"name": name, "version": "1.0.0"},
    }
    _write_json(edir / "engine.json", data)
    _write_json(edir / "engine.2-0-0.json", data)
    return edir


def _project(tmp_path, name="org.test.project"):
    pdir = tmp_path / "project"
    pdir.mkdir(exist_ok=True)
    _write_json(pdir / "project.2-0-0.json", {
        "$schemaVersion": "2.0.0",
        "project": {"name": name, "version": "1.0.0"},
    })
    return pdir


class TestWorkspaceCreate:
    def test_create_needs_engine_or_project(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        result = runner.invoke(workspace, ["create", "ws1"])
        assert result.exit_code == 1

    def test_create_with_engine(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _engine(tmp_path)
        mp = _manifest(tmp_path)
        output = tmp_path / "ws_out"
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(workspace, [
                "create", "ws1",
                "--engine", str(edir),
                "--output", str(output),
            ])
        assert result.exit_code == 0

    def test_create_already_exists(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _engine(tmp_path)
        output = tmp_path / "ws_existing"
        output.mkdir()
        # Pre-create the target dir (output / name)
        (output / "ws1").mkdir()
        runner = CliRunner()
        result = runner.invoke(workspace, [
            "create", "ws1",
            "--engine", str(edir),
            "--output", str(output),
        ])
        assert result.exit_code == 1
        assert "already exists" in result.output


# ── B: Command helper tests ────────────────────────────────────────

class TestBuildWorkspaceMeta:
    """Tests for _build_workspace_meta with resolved_candidates."""

    def test_with_candidates(self):
        from o3de_pilot.commands.workspace import _build_workspace_meta
        cands = [
            {"name": "org.o3de.engine.o3de", "version": "1.0.0",
             "object_type": "engine", "status": "local", "path": "/e"},
            {"name": "org.o3de.gem.x", "version": "0.1.0",
             "object_type": "gem", "status": "unknown"},
        ]
        meta = _build_workspace_meta(
            name="test-ws", root_path=Path("/root"), root_type="engine",
            sources=["/root"], overlays=[], resolved_candidates=cands,
        )
        assert len(meta.resolved_candidates) == 2
        assert meta.resolved_candidates[0].name == "org.o3de.engine.o3de"
        assert meta.resolved_candidates[1].status == "unknown"

    def test_without_candidates(self):
        from o3de_pilot.commands.workspace import _build_workspace_meta
        meta = _build_workspace_meta(
            name="no-cands", root_path=Path("/root"), root_type="project",
            sources=["/root"], overlays=[],
        )
        assert meta.resolved_candidates == []


class TestFindEnginePath:
    """Tests for _find_engine_path helper."""

    def _meta(self, **kwargs):
        from o3de_pilot.commands.workspace import _build_workspace_meta
        defaults = dict(name="ws", root_path=Path("/root"), root_type="engine",
                        sources=["/root"], overlays=[])
        defaults.update(kwargs)
        return _build_workspace_meta(**defaults)

    def test_from_candidates(self):
        from o3de_pilot.commands.workspace import _find_engine_path
        meta = self._meta(resolved_candidates=[
            {"name": "org.o3de.engine.o3de", "version": "1.0.0",
             "object_type": "engine", "status": "local", "path": "/eng"},
        ])
        assert _find_engine_path(meta) == Path("/eng")

    def test_fallback_to_root_object(self):
        from o3de_pilot.commands.workspace import _find_engine_path
        meta = self._meta(root_path=Path("/my-engine"), root_type="engine")
        assert _find_engine_path(meta) == Path("/my-engine")

    def test_none_when_no_engine(self):
        from o3de_pilot.commands.workspace import _find_engine_path
        meta = self._meta(root_type="project", resolved_candidates=[
            {"name": "org.o3de.gem.x", "version": "0.1.0",
             "object_type": "gem", "status": "local", "path": "/g"},
        ])
        assert _find_engine_path(meta) is None


class TestFindProjectPath:
    """Tests for _find_project_path helper."""

    def _meta(self, **kwargs):
        from o3de_pilot.commands.workspace import _build_workspace_meta
        defaults = dict(name="ws", root_path=Path("/root"), root_type="engine",
                        sources=["/root"], overlays=[])
        defaults.update(kwargs)
        return _build_workspace_meta(**defaults)

    def test_from_candidates(self):
        from o3de_pilot.commands.workspace import _find_project_path
        meta = self._meta(resolved_candidates=[
            {"name": "org.o3de.project.myproj", "version": "1.0.0",
             "object_type": "project", "status": "local", "path": "/proj"},
        ])
        assert _find_project_path(meta) == Path("/proj")

    def test_fallback_to_root_object(self):
        from o3de_pilot.commands.workspace import _find_project_path
        meta = self._meta(root_path=Path("/proj"), root_type="project")
        assert _find_project_path(meta) == Path("/proj")

    def test_none_when_no_project(self):
        from o3de_pilot.commands.workspace import _find_project_path
        meta = self._meta(resolved_candidates=[
            {"name": "org.o3de.engine.o3de", "version": "1.0.0",
             "object_type": "engine", "status": "local", "path": "/e"},
        ])
        assert _find_project_path(meta) is None


# ── C: Build command CLI tests ─────────────────────────────────────

def _workspace_meta_json(
    root_type="engine",
    root_object="/engine",
    candidates=None,
):
    """Build a minimal workspace.json dict for testing."""
    data = {
        "$schema": "https://canonical.o3de.org/o3de-workspace-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "workspace": {"name": "test-ws"},
        "created": "2026-05-31T12:00:00",
        "root_object": root_object,
        "root_type": root_type,
        "sources": [root_object],
    }
    if candidates:
        data["resolved_candidates"] = candidates
    return data


def _create_ws_dir(tmp_path, meta_data):
    """Create a workspace directory with metadata."""
    ws = tmp_path / "test-ws"
    ws.mkdir()
    (ws / "workspace.json").write_text(json.dumps(meta_data, indent=2))
    return ws


class TestBuildCommandErrors:
    """Build command error cases."""

    def test_nonexistent_workspace(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path / "workspaces"):
            result = runner.invoke(workspace, ["build", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_invalid_workspace_no_meta(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = tmp_path / "empty-ws"
        ws.mkdir()
        runner = CliRunner()
        result = runner.invoke(workspace, ["build", str(ws)])
        assert result.exit_code == 1
        assert "Not a valid workspace" in result.output

    def test_no_engine_in_metadata(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        meta = _workspace_meta_json(
            root_type="gem", root_object="/some/gem",
            candidates=[
                {"name": "org.o3de.gem.x", "version": "1.0.0",
                 "object_type": "gem", "status": "local", "path": "/g"},
            ],
        )
        ws = _create_ws_dir(tmp_path, meta)
        runner = CliRunner()
        result = runner.invoke(workspace, ["build", str(ws)])
        assert result.exit_code == 1
        assert "No engine found" in result.output


class TestBuildCommandCMake:
    """Build command cmake invocation tests."""

    def _ws_with_engine_and_project(self, tmp_path):
        """Create a workspace dir with engine + project candidates."""
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.22)")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.22)")

        meta = _workspace_meta_json(
            root_type="project", root_object=str(project_dir),
            candidates=[
                {"name": "org.o3de.engine.o3de", "version": "1.0.0",
                 "object_type": "engine", "status": "local",
                 "path": str(engine_dir)},
                {"name": "org.o3de.project.myproj", "version": "1.0.0",
                 "object_type": "project", "status": "local",
                 "path": str(project_dir)},
            ],
        )
        return _create_ws_dir(tmp_path, meta), engine_dir, project_dir

    def test_configure_only(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, ["build", str(ws), "--configure-only"])

        assert result.exit_code == 0, result.output
        # Should have exactly 1 call (configure), no build
        assert len(calls) == 1
        assert calls[0][0] == "cmake"
        assert "-S" in calls[0]
        assert "--build" not in calls[0]

    def test_project_centric_mode(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=Path("/tp")):
            result = runner.invoke(workspace, [
                "build", str(ws), "--config", "debug",
            ])

        assert result.exit_code == 0, result.output
        assert len(calls) == 2  # configure + build

        # Configure: -S <project>
        cfg = calls[0]
        assert "-S" in cfg
        s_idx = cfg.index("-S")
        assert cfg[s_idx + 1] == str(project_dir)
        assert any(a.startswith("-DLY_3RDPARTY_PATH=") for a in cfg)

        # Build: --config Debug
        bld = calls[1]
        assert "--build" in bld
        assert "--config" in bld
        config_idx = bld.index("--config")
        assert bld[config_idx + 1] == "Debug"

    def test_engine_centric_mode(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--engine-centric",
            ])

        assert result.exit_code == 0, result.output
        cfg = calls[0]
        s_idx = cfg.index("-S")
        assert cfg[s_idx + 1] == str(engine_dir)
        assert any(a.startswith("-DLY_PROJECTS=") for a in cfg)

    def test_target_passed(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--target", "Editor",
            ])

        assert result.exit_code == 0, result.output
        bld = calls[1]  # build command
        assert "--target" in bld
        target_idx = bld.index("--target")
        assert bld[target_idx + 1] == "Editor"

    def test_skip_configure_when_cache_exists(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)

        # Pre-create the build dir with CMakeCache.txt
        import sys
        platform_dir = {"win32": "windows", "linux": "linux", "darwin": "mac"}.get(
            sys.platform, sys.platform)
        build_dir = project_dir / "build" / platform_dir
        build_dir.mkdir(parents=True)
        (build_dir / "CMakeCache.txt").write_text("# fake cache")

        runner = CliRunner()
        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, ["build", str(ws)])

        assert result.exit_code == 0, result.output
        # Should be just 1 call (build only, no configure)
        assert len(calls) == 1
        assert "--build" in calls[0]

    def test_reconfigure_forces_configure(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)

        import sys
        platform_dir = {"win32": "windows", "linux": "linux", "darwin": "mac"}.get(
            sys.platform, sys.platform)
        build_dir = project_dir / "build" / platform_dir
        build_dir.mkdir(parents=True)
        (build_dir / "CMakeCache.txt").write_text("# fake cache")

        runner = CliRunner()
        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--reconfigure",
            ])

        assert result.exit_code == 0, result.output
        # Should be 2 calls: reconfigure + build
        assert len(calls) == 2
        assert "-S" in calls[0]
        assert "--build" in calls[1]

    def test_preset_mode(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--preset", "windows-default",
            ])

        assert result.exit_code == 0, result.output
        cfg = calls[0]
        assert "--preset" in cfg
        preset_idx = cfg.index("--preset")
        assert cfg[preset_idx + 1] == "windows-default"
        # Preset mode should not use -B
        assert "-B" not in cfg


# ── D: Integration — create persists candidates ────────────────────

class TestCreatePersistsCandidates:
    """workspace create should persist resolved_candidates in metadata."""

    def test_create_writes_candidates_field(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _engine(tmp_path)
        mp = _manifest(tmp_path)
        output = tmp_path / "ws_out"
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            result = runner.invoke(workspace, [
                "create", "ws1",
                "--engine", str(edir),
                "--output", str(output),
            ])
        assert result.exit_code == 0, result.output

        # Read the written metadata and verify resolved_candidates key exists
        ws_json_path = output / "ws1" / "workspace.json"
        assert ws_json_path.exists(), f"workspace.json not found at {ws_json_path}"
        data = json.loads(ws_json_path.read_text())
        assert "resolved_candidates" in data
        # It should be a list (may be empty if engine wasn't registered in manifest)
        assert isinstance(data["resolved_candidates"], list)


# ── E: Auto-install (J2) tests ─────────────────────────────────────

class TestAutoInstall:
    """Tests for --auto-install flag on workspace create."""

    def test_auto_install_requires_include_store(self, tmp_path):
        """--auto-install without --include-store warns the user."""
        from o3de_pilot.commands.workspace import workspace
        edir = _engine(tmp_path)
        mp = _manifest(tmp_path)
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # Mock solver to return remote candidates
        mock_solve = MagicMock()
        mock_solve.is_resolved = True
        mock_solve.remote_count = 2
        mock_solve.unknown_count = 0
        mock_solve.local_count = 1
        mock_solve.candidates = {}
        mock_solve.children = {}
        mock_solve.overlays = {}

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.solve_for_workspace",
                   return_value=mock_solve), \
             patch("o3de_pilot.commands.workspace.Resolver") as MockResolver:
            r = MockResolver.return_value
            r.resolve.return_value = None
            r.manifest_remotes = []
            r.objects = {"org.test.engine": MagicMock(path=Path(edir).resolve())}
            result = runner.invoke(workspace, [
                "create", "ws-ai",
                "--engine", str(edir),
                "--output", str(output),
                "--auto-install",
            ])
        assert result.exit_code == 0, result.output
        assert "--auto-install requires --include-store" in result.output

    def test_auto_install_calls_resolver(self, tmp_path):
        """--auto-install with --include-store calls auto_install_missing."""
        from o3de_pilot.commands.workspace import workspace
        edir = _engine(tmp_path)
        mp = _manifest(tmp_path)
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # First solve returns remote deps, second solve after install returns all local
        mock_solve_1 = MagicMock()
        mock_solve_1.is_resolved = True
        mock_solve_1.remote_count = 1
        mock_solve_1.unknown_count = 0
        mock_solve_1.local_count = 1
        mock_solve_1.candidates = {}
        mock_solve_1.children = {}
        mock_solve_1.overlays = {}

        mock_solve_2 = MagicMock()
        mock_solve_2.is_resolved = True
        mock_solve_2.remote_count = 0
        mock_solve_2.unknown_count = 0
        mock_solve_2.local_count = 2
        mock_solve_2.candidates = {}
        mock_solve_2.children = {}
        mock_solve_2.overlays = {}

        solve_calls = [mock_solve_1, mock_solve_2]

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.solve_for_workspace",
                   side_effect=solve_calls), \
             patch("o3de_pilot.commands.workspace.Resolver") as MockResolver, \
             patch("o3de_pilot.core.store.Store") as MockStore:
            r = MockResolver.return_value
            r.resolve.return_value = None
            r.manifest_remotes = ["https://example.com/repo.json"]
            r.objects = {"org.test.engine": MagicMock(path=Path(edir).resolve())}
            r.auto_install_missing.return_value = [
                {"name": "org.o3de.gem.x", "version": "1.0.0",
                 "type": "gem", "path": "/gems/x", "source": "https://example.com"}
            ]

            s = MockStore.return_value
            s.refresh_sync.return_value = 1

            result = runner.invoke(workspace, [
                "create", "ws-ai",
                "--engine", str(edir),
                "--output", str(output),
                "--include-store",
                "--auto-install",
            ])

        assert result.exit_code == 0, result.output
        assert "Installed 1 remote dependencies" in result.output
        # auto_install_missing should have been called with confirm=True
        r.auto_install_missing.assert_called_once()
        call_kwargs = r.auto_install_missing.call_args
        assert call_kwargs.kwargs.get("confirm") is True or call_kwargs[1].get("confirm") is True

    def test_auto_install_skipped_when_no_remote(self, tmp_path):
        """--auto-install does nothing when there are no remote deps."""
        from o3de_pilot.commands.workspace import workspace
        edir = _engine(tmp_path)
        mp = _manifest(tmp_path)
        output = tmp_path / "ws_out"
        runner = CliRunner()

        mock_solve = MagicMock()
        mock_solve.is_resolved = True
        mock_solve.remote_count = 0
        mock_solve.unknown_count = 0
        mock_solve.local_count = 3
        mock_solve.candidates = {}
        mock_solve.children = {}
        mock_solve.overlays = {}

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.solve_for_workspace",
                   return_value=mock_solve), \
             patch("o3de_pilot.commands.workspace.Resolver") as MockResolver, \
             patch("o3de_pilot.core.store.Store") as MockStore:
            r = MockResolver.return_value
            r.resolve.return_value = None
            r.manifest_remotes = ["https://example.com/repo.json"]
            r.objects = {"org.test.engine": MagicMock(path=Path(edir).resolve())}

            s = MockStore.return_value
            s.refresh_sync.return_value = 0

            result = runner.invoke(workspace, [
                "create", "ws-ai",
                "--engine", str(edir),
                "--output", str(output),
                "--include-store",
                "--auto-install",
            ])

        assert result.exit_code == 0, result.output
        # auto_install_missing should NOT have been called
        r.auto_install_missing.assert_not_called()
        assert "Installed" not in result.output


# ── F: CMakePresets (K2) tests ─────────────────────────────────────

class TestEnsureProjectCMakePresets:
    """Tests for _ensure_project_cmake_presets helper."""

    def test_creates_preset_when_missing(self, tmp_path):
        from o3de_pilot.commands.workspace import _ensure_project_cmake_presets
        project = tmp_path / "project"
        project.mkdir()
        engine = tmp_path / "engine"
        engine.mkdir()
        (engine / "CMakePresets.json").write_text("{}")

        result = _ensure_project_cmake_presets(project, engine)
        assert result is True

        preset = json.loads((project / "CMakePresets.json").read_text())
        assert "include" in preset
        assert len(preset["include"]) == 1
        assert (engine / "CMakePresets.json").as_posix() in preset["include"][0]

    def test_noop_when_already_included(self, tmp_path):
        from o3de_pilot.commands.workspace import _ensure_project_cmake_presets
        project = tmp_path / "project"
        project.mkdir()
        engine = tmp_path / "engine"
        engine.mkdir()
        engine_presets = engine / "CMakePresets.json"
        engine_presets.write_text("{}")

        # Pre-create with correct include
        (project / "CMakePresets.json").write_text(json.dumps({
            "version": 4,
            "include": [engine_presets.as_posix()],
        }))

        result = _ensure_project_cmake_presets(project, engine)
        assert result is False

    def test_replaces_stale_engine_include(self, tmp_path):
        from o3de_pilot.commands.workspace import _ensure_project_cmake_presets
        project = tmp_path / "project"
        project.mkdir()
        engine = tmp_path / "engine"
        engine.mkdir()
        (engine / "CMakePresets.json").write_text("{}")

        # Pre-create with wrong engine
        (project / "CMakePresets.json").write_text(json.dumps({
            "version": 4,
            "include": ["/old/engine/CMakePresets.json"],
        }))

        result = _ensure_project_cmake_presets(project, engine)
        assert result is True

        preset = json.loads((project / "CMakePresets.json").read_text())
        assert len(preset["include"]) == 1
        assert (engine / "CMakePresets.json").as_posix() in preset["include"][0]

    def test_noop_when_no_engine_presets(self, tmp_path):
        from o3de_pilot.commands.workspace import _ensure_project_cmake_presets
        project = tmp_path / "project"
        project.mkdir()
        engine = tmp_path / "engine"
        engine.mkdir()
        # No CMakePresets.json in engine

        result = _ensure_project_cmake_presets(project, engine)
        assert result is False

    def test_preserves_version_field(self, tmp_path):
        from o3de_pilot.commands.workspace import _ensure_project_cmake_presets
        project = tmp_path / "project"
        project.mkdir()
        engine = tmp_path / "engine"
        engine.mkdir()
        (engine / "CMakePresets.json").write_text("{}")

        # Pre-create with different version and stale include
        (project / "CMakePresets.json").write_text(json.dumps({
            "version": 6,
            "cmakeMinimumRequired": {"major": 3, "minor": 28, "patch": 0},
            "include": ["/old/CMakePresets.json"],
        }))

        _ensure_project_cmake_presets(project, engine)
        preset = json.loads((project / "CMakePresets.json").read_text())
        assert preset["version"] == 6
        assert preset["cmakeMinimumRequired"]["minor"] == 28


class TestBuildCommandCMakePresets:
    """Build command integration with CMakePresets pre-configure."""

    def test_project_centric_updates_presets(self, tmp_path):
        """Project-centric build should call _ensure_project_cmake_presets."""
        from o3de_pilot.commands.workspace import workspace

        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "CMakePresets.json").write_text("{}")

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        meta = _workspace_meta_json(
            root_type="project", root_object=str(project_dir),
            candidates=[
                {"name": "org.o3de.engine.o3de", "version": "1.0.0",
                 "object_type": "engine", "status": "local",
                 "path": str(engine_dir)},
                {"name": "org.o3de.project.myproj", "version": "1.0.0",
                 "object_type": "project", "status": "local",
                 "path": str(project_dir)},
            ],
        )
        ws = _create_ws_dir(tmp_path, meta)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--configure-only",
            ])

        assert result.exit_code == 0, result.output
        # CMakePresets.json should have been created in the project
        preset_path = project_dir / "CMakePresets.json"
        assert preset_path.exists()
        preset = json.loads(preset_path.read_text())
        assert (engine_dir / "CMakePresets.json").as_posix() in preset["include"][0]

    def test_engine_centric_skips_presets(self, tmp_path):
        """Engine-centric build should NOT touch project presets."""
        from o3de_pilot.commands.workspace import workspace

        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "CMakePresets.json").write_text("{}")

        project_dir = tmp_path / "project"
        project_dir.mkdir()

        meta = _workspace_meta_json(
            root_type="project", root_object=str(project_dir),
            candidates=[
                {"name": "org.o3de.engine.o3de", "version": "1.0.0",
                 "object_type": "engine", "status": "local",
                 "path": str(engine_dir)},
                {"name": "org.o3de.project.myproj", "version": "1.0.0",
                 "object_type": "project", "status": "local",
                 "path": str(project_dir)},
            ],
        )
        ws = _create_ws_dir(tmp_path, meta)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--engine-centric", "--configure-only",
            ])

        assert result.exit_code == 0, result.output
        # Project's CMakePresets.json should NOT exist
        assert not (project_dir / "CMakePresets.json").exists()


# ── K5: Generator selection ─────────────────────────────────────────

class TestGeneratorSelection:
    """K5: _select_generator and --generator CLI option."""

    def test_auto_windows(self):
        from o3de_pilot.commands.workspace import _select_generator
        with patch("o3de_pilot.commands.workspace.sys") as mock_sys:
            mock_sys.platform = "win32"
            assert _select_generator("auto") == "Visual Studio 17 2022"

    def test_auto_linux(self):
        from o3de_pilot.commands.workspace import _select_generator
        with patch("o3de_pilot.commands.workspace.sys") as mock_sys:
            mock_sys.platform = "linux"
            assert _select_generator("auto") == "Ninja Multi-Config"

    def test_auto_mac(self):
        from o3de_pilot.commands.workspace import _select_generator
        with patch("o3de_pilot.commands.workspace.sys") as mock_sys:
            mock_sys.platform = "darwin"
            assert _select_generator("auto") == "Xcode"

    def test_none_uses_platform_default(self):
        from o3de_pilot.commands.workspace import _select_generator
        # None behaves same as auto
        result = _select_generator(None)
        assert result is not None

    def test_alias_vs(self):
        from o3de_pilot.commands.workspace import _select_generator
        assert _select_generator("vs") == "Visual Studio 17 2022"

    def test_alias_ninja(self):
        from o3de_pilot.commands.workspace import _select_generator
        assert _select_generator("ninja") == "Ninja Multi-Config"

    def test_alias_xcode(self):
        from o3de_pilot.commands.workspace import _select_generator
        assert _select_generator("xcode") == "Xcode"

    def test_alias_makefiles(self):
        from o3de_pilot.commands.workspace import _select_generator
        assert _select_generator("makefiles") == "Unix Makefiles"

    def test_passthrough_custom(self):
        from o3de_pilot.commands.workspace import _select_generator
        assert _select_generator("My Custom Gen") == "My Custom Gen"


class TestGeneratorInBuild:
    """K5: --generator flag wired into build configure command."""

    def _ws_with_engine_and_project(self, tmp_path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        meta = _workspace_meta_json(
            root_type="project", root_object=str(project_dir),
            candidates=[
                {"name": "org.o3de.engine.o3de", "version": "1.0.0",
                 "object_type": "engine", "status": "local",
                 "path": str(engine_dir)},
                {"name": "org.o3de.project.myproj", "version": "1.0.0",
                 "object_type": "project", "status": "local",
                 "path": str(project_dir)},
            ],
        )
        return _create_ws_dir(tmp_path, meta), engine_dir, project_dir

    def test_generator_flag_in_configure_cmd(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--configure-only", "-G", "ninja",
            ])

        assert result.exit_code == 0, result.output
        cfg = calls[0]
        assert any(a == "-GNinja Multi-Config" for a in cfg)

    def test_default_generator_added(self, tmp_path):
        """Without explicit --generator, auto-detect should still add -G."""
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--configure-only",
            ])

        assert result.exit_code == 0, result.output
        cfg = calls[0]
        # Should have a -G flag from auto-detection
        assert any(a.startswith("-G") for a in cfg)

    def test_preset_mode_no_generator(self, tmp_path):
        """Preset mode should NOT add a -G flag."""
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--preset", "test-preset", "--configure-only",
            ])

        assert result.exit_code == 0, result.output
        cfg = calls[0]
        # Preset mode uses --preset, not -B/-G
        assert "--preset" in cfg
        assert not any(a.startswith("-G") for a in cfg)


# ── K5: _run_cmake streaming + cancel ────────────────────────────────

class TestRunCmake:
    """K5: _run_cmake output streaming and cancel support."""

    def test_streams_output_line_by_line(self):
        from o3de_pilot.commands.workspace import _run_cmake

        lines_received = []

        mock_proc = MagicMock()
        mock_proc.stdout = iter(["line1\n", "line2\n", "done\n"])
        mock_proc.wait.return_value = 0

        with patch("o3de_pilot.commands.workspace.subprocess.Popen", return_value=mock_proc):
            rc = _run_cmake(
                ["cmake", "--version"],
                cwd=Path("."),
                on_line=lambda l: lines_received.append(l),
            )

        assert rc == 0
        assert lines_received == ["line1", "line2", "done"]

    def test_returns_nonzero_on_failure(self):
        from o3de_pilot.commands.workspace import _run_cmake

        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.return_value = 1

        with patch("o3de_pilot.commands.workspace.subprocess.Popen", return_value=mock_proc):
            rc = _run_cmake(["cmake", "bad"], cwd=Path("."))

        assert rc == 1

    def test_cancel_returns_sigterm(self):
        from o3de_pilot.commands.workspace import _run_cmake

        mock_proc = MagicMock()
        # Simulate KeyboardInterrupt during iteration
        mock_proc.stdout = MagicMock()
        mock_proc.stdout.__iter__ = MagicMock(side_effect=KeyboardInterrupt)
        mock_proc.pid = 12345

        with patch("o3de_pilot.commands.workspace.subprocess.Popen", return_value=mock_proc), \
             patch("o3de_pilot.commands.workspace.subprocess.run"):
            rc = _run_cmake(["cmake", "long-build"], cwd=Path("."))

        assert rc == -15


# ── K6: Third-party path resolution chain ────────────────────────────

class TestThirdPartyResolution:
    """K6: _find_third_party_path full resolution chain."""

    def test_workspace_meta_takes_priority(self, tmp_path):
        from o3de_pilot.commands.workspace import _find_third_party_path

        tp_dir = tmp_path / "ws_tp"
        tp_dir.mkdir()

        meta = MagicMock()
        meta.third_party_path = str(tp_dir)

        result = _find_third_party_path(meta=meta)
        assert result == tp_dir

    def test_engine_json_second_priority(self, tmp_path):
        from o3de_pilot.commands.workspace import _find_third_party_path

        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        tp_dir = tmp_path / "engine_tp"
        tp_dir.mkdir()

        # Write engine.2-0-0.json with third_party_path
        engine_json = {"engine": {"third_party_path": str(tp_dir)}}
        (engine_dir / "engine.2-0-0.json").write_text(json.dumps(engine_json))

        meta = MagicMock()
        meta.third_party_path = None  # No workspace-level setting

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=None):
            result = _find_third_party_path(meta=meta, engine_path=engine_dir)

        assert result == tp_dir

    def test_user_config_third_priority(self, tmp_path):
        from o3de_pilot.commands.workspace import _find_third_party_path

        tp_dir = tmp_path / "user_tp"
        tp_dir.mkdir()

        meta = MagicMock()
        meta.third_party_path = None

        mock_config = MagicMock()
        mock_config.get.return_value = str(tp_dir)

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=None), \
             patch("o3de_pilot.core.config.get_config", return_value=mock_config):
            result = _find_third_party_path(meta=meta)

        assert result == tp_dir

    def test_manifest_fourth_priority(self, tmp_path):
        from o3de_pilot.commands.workspace import _find_third_party_path

        tp_dir = tmp_path / "manifest_tp"
        tp_dir.mkdir()

        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"default": {"third_party_path": str(tp_dir)}}))

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=manifest):
            result = _find_third_party_path()

        assert result == tp_dir

    def test_default_fallback(self, tmp_path):
        from o3de_pilot.commands.workspace import _find_third_party_path

        default_dir = tmp_path / "3rdParty"
        default_dir.mkdir()

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=None), \
             patch("o3de_pilot.core.paths.get_third_party_path", return_value=default_dir):
            result = _find_third_party_path()

        assert result == default_dir

    def test_none_when_nothing_exists(self):
        from o3de_pilot.commands.workspace import _find_third_party_path

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=None), \
             patch("o3de_pilot.core.paths.get_third_party_path",
                   return_value=Path("/nonexistent/3rdParty")):
            result = _find_third_party_path()

        assert result is None

    def test_skips_nonexistent_candidates(self, tmp_path):
        """Each candidate path must exist to be used."""
        from o3de_pilot.commands.workspace import _find_third_party_path

        real_dir = tmp_path / "real_tp"
        real_dir.mkdir()

        meta = MagicMock()
        meta.third_party_path = "/does/not/exist"

        manifest = tmp_path / "manifest.json"
        manifest.write_text(json.dumps({"default": {"third_party_path": str(real_dir)}}))

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=manifest):
            result = _find_third_party_path(meta=meta)

        assert result == real_dir


# ── L2: --json output ───────────────────────────────────────────────

class TestBuildJsonOutput:
    """L2: build command --json structured output."""

    def _ws_with_engine_and_project(self, tmp_path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        meta = _workspace_meta_json(
            root_type="project", root_object=str(project_dir),
            candidates=[
                {"name": "org.o3de.engine.o3de", "version": "1.0.0",
                 "object_type": "engine", "status": "local",
                 "path": str(engine_dir)},
                {"name": "org.o3de.project.myproj", "version": "1.0.0",
                 "object_type": "project", "status": "local",
                 "path": str(project_dir)},
            ],
        )
        return _create_ws_dir(tmp_path, meta), engine_dir, project_dir

    def test_json_success_output(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--json", "--config", "debug",
            ])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["config"] == "Debug"
        assert data["data"]["mode"] == "project-centric"

    def test_json_configure_only_output(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        def mock_run_cmake(cmd, **kwargs):
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--json", "--configure-only",
            ])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["phase"] == "configure"

    def test_json_error_not_found(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path / "workspaces"):
            result = runner.invoke(workspace, ["build", "nonexistent", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert data["code"] == "E_WS_NOT_FOUND"

    def test_json_error_no_engine(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        meta = _workspace_meta_json(
            root_type="gem", root_object="/some/gem",
            candidates=[
                {"name": "org.o3de.gem.x", "version": "1.0.0",
                 "object_type": "gem", "status": "local", "path": "/g"},
            ],
        )
        ws = _create_ws_dir(tmp_path, meta)
        runner = CliRunner()
        result = runner.invoke(workspace, ["build", str(ws), "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert data["code"] == "E_NO_ENGINE"

    def test_json_build_failed(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        call_count = [0]
        def mock_run_cmake(cmd, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:  # build step
                return 1
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--json",
            ])

        assert result.exit_code != 0
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert data["code"] == "E_BUILD_FAILED"


# ── L2: JSON output helper unit tests ────────────────────────────────

class TestJsonOutputHelper:
    """L2: json_output module."""

    def test_json_response_ok(self):
        from o3de_pilot.core.json_output import json_response
        result = json.loads(json_response(data={"key": "value"}))
        assert result["status"] == "ok"
        assert result["data"]["key"] == "value"

    def test_json_response_with_warnings(self):
        from o3de_pilot.core.json_output import json_response
        result = json.loads(json_response(data={}, warnings=["w1"]))
        assert result["warnings"] == ["w1"]

    def test_json_error_with_code(self):
        from o3de_pilot.core.json_output import json_error
        result = json.loads(json_error("bad", code="E_TEST"))
        assert result["status"] == "error"
        assert result["error"] == "bad"
        assert result["code"] == "E_TEST"

    def test_json_error_without_code(self):
        from o3de_pilot.core.json_output import json_error
        result = json.loads(json_error("oops"))
        assert result["status"] == "error"
        assert "code" not in result


# ── L3: --dry-run ────────────────────────────────────────────────────

class TestBuildDryRun:
    """L3: build command --dry-run support."""

    def _ws_with_engine_and_project(self, tmp_path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        meta = _workspace_meta_json(
            root_type="project", root_object=str(project_dir),
            candidates=[
                {"name": "org.o3de.engine.o3de", "version": "1.0.0",
                 "object_type": "engine", "status": "local",
                 "path": str(engine_dir)},
                {"name": "org.o3de.project.myproj", "version": "1.0.0",
                 "object_type": "project", "status": "local",
                 "path": str(project_dir)},
            ],
        )
        return _create_ws_dir(tmp_path, meta), engine_dir, project_dir

    def test_dry_run_no_execution(self, tmp_path):
        """--dry-run should not call _run_cmake."""
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        calls = []
        def mock_run_cmake(cmd, **kwargs):
            calls.append(cmd)
            return 0

        with patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--dry-run",
            ])

        assert result.exit_code == 0, result.output
        assert len(calls) == 0  # Nothing executed

    def test_dry_run_shows_commands(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        with patch("o3de_pilot.commands.workspace._run_cmake", return_value=0), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--dry-run",
            ])

        assert result.exit_code == 0, result.output
        assert "cmake" in result.output.lower()

    def test_dry_run_json_output(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        with patch("o3de_pilot.commands.workspace._run_cmake", return_value=0), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--dry-run", "--json",
            ])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["dry_run"] is True
        assert len(data["data"]["commands"]) >= 1
        assert all("cmake" in c for c in data["data"]["commands"])

    def test_dry_run_configure_only(self, tmp_path):
        """--dry-run --configure-only should show only configure command."""
        from o3de_pilot.commands.workspace import workspace
        ws, engine_dir, project_dir = self._ws_with_engine_and_project(tmp_path)
        runner = CliRunner()

        with patch("o3de_pilot.commands.workspace._run_cmake", return_value=0), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=None):
            result = runner.invoke(workspace, [
                "build", str(ws), "--dry-run", "--configure-only", "--json",
            ])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["data"]["dry_run"] is True
        assert len(data["data"]["commands"]) == 1
        assert "-S" in data["data"]["commands"][0]


# ── L2/L3: delete --json / --dry-run ─────────────────────────────────

class TestDeleteJsonDryRun:
    """L2/L3: delete command --json and --dry-run."""

    def _make_ws(self, tmp_path):
        meta = _workspace_meta_json(
            root_type="engine", root_object="/e",
            candidates=[{"name": "e", "version": "1.0.0",
                         "object_type": "engine", "status": "local",
                         "path": "/e"}],
        )
        return _create_ws_dir(tmp_path, meta)

    def test_delete_json_success(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = self._make_ws(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace._unregister_workspace"):
            result = runner.invoke(workspace, ["delete", str(ws), "--force", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["action"] == "deleted"

    def test_delete_json_not_found(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path / "workspaces"):
            result = runner.invoke(workspace, ["delete", "nope", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert data["code"] == "E_WS_NOT_FOUND"

    def test_delete_dry_run(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = self._make_ws(tmp_path)
        runner = CliRunner()
        result = runner.invoke(workspace, ["delete", str(ws), "--dry-run"])
        assert result.exit_code == 0, result.output
        assert ws.exists()  # Not actually deleted
        assert "Would delete" in result.output

    def test_delete_dry_run_json(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = self._make_ws(tmp_path)
        runner = CliRunner()
        result = runner.invoke(workspace, ["delete", str(ws), "--dry-run", "--json"])
        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["data"]["dry_run"] is True
        assert data["data"]["action"] == "delete"
        assert ws.exists()  # Not deleted


# ── L2: update --json ────────────────────────────────────────────────

class TestUpdateJson:
    """L2: update command --json."""

    def _make_ws_with_sources(self, tmp_path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        (engine_dir / "engine.json").write_text(json.dumps({"engine_name": "test"}))
        meta = _workspace_meta_json(
            root_type="engine", root_object=str(engine_dir),
            candidates=[{"name": "e", "version": "1.0.0",
                         "object_type": "engine", "status": "local",
                         "path": str(engine_dir)}],
        )
        meta["sources"] = [str(engine_dir)]
        meta["overlays"] = []
        return _create_ws_dir(tmp_path, meta), engine_dir

    def test_update_json_not_found(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        runner = CliRunner()
        with patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                    return_value=tmp_path / "workspaces"):
            result = runner.invoke(workspace, ["update", "nope", "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert data["code"] == "E_WS_NOT_FOUND"

    def test_update_json_invalid(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        ws = tmp_path / "bad-ws"
        ws.mkdir()
        runner = CliRunner()
        result = runner.invoke(workspace, ["update", str(ws), "--json"])
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data["status"] == "error"
        assert data["code"] == "E_WS_INVALID"
