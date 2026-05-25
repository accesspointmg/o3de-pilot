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
        runner = CliRunner()
        result = runner.invoke(workspace, [
            "create", "ws1",
            "--engine", str(edir),
            "--output", str(output),
        ])
        assert result.exit_code == 1
        assert "already exists" in result.output
