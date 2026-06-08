# O3DE Pilot CLI - CLI Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for CLI commands."""

import json
from click.testing import CliRunner
from o3de_pilot.__main__ import cli


def test_cli_version():
    """Test that --version works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "o3de-pilot" in result.output


def test_cli_help():
    """Test that --help lists all expected command groups."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "O3DE Pilot" in result.output
    for cmd in ["project", "gem", "engine", "template", "registry",
                 "manifest", "workspace", "ai", "config", "publish",
                 "audit", "deps"]:
        assert cmd in result.output, f"Missing command group: {cmd}"


def test_project_list(mock_manifest, tmp_path, runner):
    """Test project list returns projects from the manifest."""
    from tests.conftest import make_gem, _write_json
    # Register a project in the manifest
    proj_dir = tmp_path / "MyProj"
    proj_dir.mkdir()
    _write_json(proj_dir / "project.2-0-0.json", {
        "$schema": "https://canonical.o3de.org/o3de-project-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "project": {"name": "org.test.project.myproj", "version": "1.0.0",
                     "display_name": "MyProj"},
    })
    manifest_data = json.loads(mock_manifest.read_text())
    manifest_data.setdefault("local", {}).setdefault("projects", []).append(proj_dir.as_posix())
    mock_manifest.write_text(json.dumps(manifest_data))

    result = runner.invoke(cli, ["project", "list"])
    assert result.exit_code == 0
    assert "myproj" in result.output.lower() or "MyProj" in result.output


def test_gem_list(mock_manifest, tmp_path, runner):
    """Test gem list returns gems from the manifest."""
    from tests.conftest import make_gem
    gem_dir = make_gem(tmp_path, "org.test.gem.alpha", "2.0.0")
    manifest_data = json.loads(mock_manifest.read_text())
    manifest_data.setdefault("local", {}).setdefault("gems", []).append(gem_dir.as_posix())
    mock_manifest.write_text(json.dumps(manifest_data))

    result = runner.invoke(cli, ["gem", "list"])
    assert result.exit_code == 0
    assert "alpha" in result.output.lower() or "org.test.gem.alpha" in result.output


def test_config_list(mock_manifest, runner):
    """Test config list shows known configuration keys."""
    result = runner.invoke(cli, ["config", "list"])
    assert result.exit_code == 0
    # Config list should show at least the ai_provider key or similar config keys
    assert len(result.output.strip()) > 0
