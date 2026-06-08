# O3DE Pilot - End-to-End Acceptance Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
End-to-end acceptance tests for the full o3de-pilot lifecycle:
  workspace create → solve → build

These tests exercise real CLI paths with mocked filesystem and subprocess
to verify the complete flow works end-to-end.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from tests.conftest import _write_json


# ── Helpers ─────────────────────────────────────────────────────────

def _extract_json(output):
    """Extract JSON from CLI output that may contain spinner/progress text."""
    idx = output.find("{")
    if idx == -1:
        raise ValueError(f"No JSON found in output: {output!r}")
    return json.loads(output[idx:])

def _setup_engine(tmp_path, name="org.test.engine", version="1.0.0"):
    """Create a minimal Schema 2.0 engine directory."""
    edir = tmp_path / "engine"
    edir.mkdir(exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        "engine": {"name": name, "version": version},
    }
    _write_json(edir / "engine.json", data)
    _write_json(edir / "engine.2-0-0.json", data)
    (edir / "CMakeLists.txt").write_text("cmake_minimum_required(VERSION 3.22)\nproject(TestEngine)\n")
    return edir


def _setup_gem(tmp_path, name="org.test.gem", version="1.0.0", subdir="gem"):
    """Create a minimal Schema 2.0 gem directory."""
    gdir = tmp_path / subdir
    gdir.mkdir(exist_ok=True, parents=True)
    data = {
        "$schemaVersion": "2.0.0",
        "gem": {"name": name, "version": version},
    }
    _write_json(gdir / "gem.json", data)
    _write_json(gdir / "gem.2-0-0.json", data)
    return gdir


def _setup_manifest(tmp_path, engines=None, gems=None):
    """Create a Schema 2.0 manifest file."""
    mp = tmp_path / "o3de_manifest.2-0-0.json"
    _write_json(mp, {
        "$schemaVersion": "2.0.0",
        "o3de_manifest": {"name": "test"},
        "local": {
            "engines": engines or [],
            "projects": [],
            "gems": gems or [],
            "templates": [],
            "repos": [],
            "overlays": [],
        },
        "remotes": [],
    })
    return mp


def _standard_patches(tmp_path, manifest_path):
    """Return a dict of standard patches for workspace commands."""
    return {
        "o3de_pilot.commands.workspace.get_manifest_path": manifest_path,
        "o3de_pilot.commands.workspace.get_resolved_manifest_path": tmp_path / "resolved.json",
        "o3de_pilot.commands.workspace.get_default_workspaces_path": tmp_path / "workspaces",
        "o3de_pilot.core.resolver.get_manifest_path": manifest_path,
        "o3de_pilot.core.resolver.get_resolved_manifest_path": tmp_path / "resolved.json",
    }


# ── E2E: Create → Verify workspace.json ────────────────────────────

class TestE2ECreateWorkspace:
    """Test that workspace create produces a valid workspace directory."""

    def test_create_produces_workspace_json(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
        output = tmp_path / "ws_out"
        runner = CliRunner()

        patches = _standard_patches(tmp_path, mp)
        with patch(list(patches.keys())[0], return_value=patches[list(patches.keys())[0]]), \
             patch(list(patches.keys())[1], return_value=patches[list(patches.keys())[1]]), \
             patch(list(patches.keys())[2], return_value=patches[list(patches.keys())[2]]), \
             patch(list(patches.keys())[3], return_value=patches[list(patches.keys())[3]]), \
             patch(list(patches.keys())[4], return_value=patches[list(patches.keys())[4]]):
            result = runner.invoke(workspace, [
                "create", "e2e-ws",
                "--engine", str(edir),
                "--output", str(output),
            ])

        assert result.exit_code == 0, f"Create failed: {result.output}"
        ws_json = output / "e2e-ws" / "workspace.json"
        assert ws_json.exists(), f"workspace.json not created"
        data = json.loads(ws_json.read_text())
        # workspace.json uses Schema 2.0 structure
        assert "workspace" in data or "name" in data
        assert data.get("$schemaVersion") == "2.0.0"

    def test_create_json_output(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
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
                "create", "e2e-json",
                "--engine", str(edir),
                "--output", str(output),
                "--json",
            ])

        assert result.exit_code == 0, f"Create --json failed: {result.output}"
        envelope = _extract_json(result.output)
        assert envelope["status"] == "ok"


# ── E2E: Create → Solve ────────────────────────────────────────────

class TestE2ECreateAndSolve:
    """Test that a created workspace can be solved."""

    def test_create_then_solve(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # Step 1: Create with --no-solve
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            r1 = runner.invoke(workspace, [
                "create", "e2e-solve",
                "--engine", str(edir),
                "--output", str(output),
                "--no-solve",
            ])
        assert r1.exit_code == 0, f"Create failed: {r1.output}"

        ws_dir = output / "e2e-solve"
        assert ws_dir.exists()

        # Step 2: Solve using the engine name (solve resolves from manifest, not path)
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=output), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            r2 = runner.invoke(workspace, ["solve", "org.test.engine"])
        assert r2.exit_code == 0, f"Solve failed: {r2.output}"


# ── E2E: Create → Build (mocked cmake) ─────────────────────────────

class TestE2ECreateAndBuild:
    """Test the full create → build flow with mocked cmake."""

    def test_create_then_build_success(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # Step 1: Create workspace
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            r1 = runner.invoke(workspace, [
                "create", "e2e-build",
                "--engine", str(edir),
                "--output", str(output),
            ])
        assert r1.exit_code == 0, f"Create failed: {r1.output}"

        # Step 2: Build with mocked cmake
        cmake_calls = []
        def mock_run_cmake(cmd, **kwargs):
            cmake_calls.append(cmd)
            return 0

        ws_dir = output / "e2e-build"
        # Ensure build directory exists for cmake
        (ws_dir / "build").mkdir(exist_ok=True)

        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=output), \
             patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=tmp_path / "3p"):
            r2 = runner.invoke(workspace, [
                "build", "e2e-build",
                "--config", "profile",
            ])
        assert r2.exit_code == 0, f"Build failed: {r2.output}"
        assert len(cmake_calls) >= 1, "cmake should have been called"

    def test_create_then_build_json(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # Create workspace
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            runner.invoke(workspace, [
                "create", "e2e-bj",
                "--engine", str(edir),
                "--output", str(output),
            ])

        # Build --json
        (output / "e2e-bj" / "build").mkdir(exist_ok=True)
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=output), \
             patch("o3de_pilot.commands.workspace._run_cmake", return_value=0), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=tmp_path / "3p"):
            r = runner.invoke(workspace, [
                "build", "e2e-bj", "--config", "profile", "--json",
            ])
        assert r.exit_code == 0, f"Build --json failed: {r.output}"
        envelope = _extract_json(r.output)
        assert envelope["status"] == "ok"


# ── E2E: Create → Delete ───────────────────────────────────────────

class TestE2ECreateAndDelete:
    """Test workspace lifecycle: create then delete."""

    def test_create_then_delete(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # Create
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            runner.invoke(workspace, [
                "create", "e2e-del",
                "--engine", str(edir),
                "--output", str(output),
            ])

        ws_dir = output / "e2e-del"
        assert ws_dir.exists()

        # Delete with --force to bypass confirmation
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=output):
            r = runner.invoke(workspace, ["delete", "e2e-del", "--force"])
        assert r.exit_code == 0, f"Delete failed: {r.output}"

    def test_create_delete_dry_run_preserves(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # Create
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            runner.invoke(workspace, [
                "create", "e2e-dry",
                "--engine", str(edir),
                "--output", str(output),
            ])

        ws_dir = output / "e2e-dry"
        assert ws_dir.exists()

        # Dry-run delete should NOT remove the directory
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=output):
            r = runner.invoke(workspace, ["delete", "e2e-dry", "--dry-run", "--force"])
        assert r.exit_code == 0, f"Dry-run delete failed: {r.output}"
        assert ws_dir.exists(), "Dry-run should NOT delete the workspace"


# ── E2E: Build Dry-Run ─────────────────────────────────────────────

class TestE2EBuildDryRun:
    """Test that build --dry-run shows commands but doesn't execute them."""

    def test_build_dry_run_no_cmake_execution(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # Create workspace
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            runner.invoke(workspace, [
                "create", "e2e-dryb",
                "--engine", str(edir),
                "--output", str(output),
            ])

        cmake_calls = []
        def mock_run_cmake(cmd, **kwargs):
            cmake_calls.append(cmd)
            return 0

        (output / "e2e-dryb" / "build").mkdir(exist_ok=True)
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=output), \
             patch("o3de_pilot.commands.workspace._run_cmake", side_effect=mock_run_cmake), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=tmp_path / "3p"):
            r = runner.invoke(workspace, [
                "build", "e2e-dryb", "--config", "profile", "--dry-run",
            ])
        assert r.exit_code == 0, f"Dry-run build failed: {r.output}"
        assert len(cmake_calls) == 0, "Dry-run should NOT call cmake"


# ── E2E: Full lifecycle JSON ───────────────────────────────────────

class TestE2EFullLifecycleJson:
    """Test the full create → build → delete with --json throughout."""

    def test_full_lifecycle_json(self, tmp_path):
        from o3de_pilot.commands.workspace import workspace
        edir = _setup_engine(tmp_path)
        mp = _setup_manifest(tmp_path, engines=[str(edir)])
        output = tmp_path / "ws_out"
        runner = CliRunner()

        # 1. Create --json
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=tmp_path / "workspaces"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"):
            r1 = runner.invoke(workspace, [
                "create", "e2e-full",
                "--engine", str(edir),
                "--output", str(output),
                "--json",
            ])
        assert r1.exit_code == 0, f"Create: {r1.output}"
        create_envelope = _extract_json(r1.output)
        assert create_envelope["status"] == "ok"

        # 2. Build --json
        (output / "e2e-full" / "build").mkdir(exist_ok=True)
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=output), \
             patch("o3de_pilot.commands.workspace._run_cmake", return_value=0), \
             patch("o3de_pilot.commands.workspace._find_third_party_path", return_value=tmp_path / "3p"):
            r2 = runner.invoke(workspace, [
                "build", "e2e-full", "--config", "profile", "--json",
            ])
        assert r2.exit_code == 0, f"Build: {r2.output}"
        build_envelope = _extract_json(r2.output)
        assert build_envelope["status"] == "ok"

        # 3. Delete --json
        with patch("o3de_pilot.commands.workspace.get_manifest_path", return_value=mp), \
             patch("o3de_pilot.commands.workspace.get_resolved_manifest_path",
                   return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.commands.workspace.get_default_workspaces_path",
                   return_value=output):
            r3 = runner.invoke(workspace, [
                "delete", "e2e-full", "--json", "--force",
            ])
        assert r3.exit_code == 0, f"Delete: {r3.output}"
        delete_envelope = _extract_json(r3.output)
        assert delete_envelope["status"] == "ok"
