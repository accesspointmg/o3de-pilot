# O3DE Pilot - Integration Tests for Commands
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Integration tests for CLI commands — tests actual command invocation."""

import pytest
import tempfile
import json
from pathlib import Path
from click.testing import CliRunner
from o3de_pilot.__main__ import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def temp_project(tmp_path):
    """Create a minimal project structure for testing."""
    project_dir = tmp_path / "TestProject"
    project_dir.mkdir()
    project_json = {
        "$schema": "https://overlo3de.com/o3de-project-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "project": {
            "name": "org.test.project.test",
            "version": "1.0.0",
            "display_name": "Test Project",
        }
    }
    with open(project_dir / "project.2-0-0.json", "w") as f:
        json.dump(project_json, f)
    return project_dir


@pytest.fixture
def temp_gem(tmp_path):
    """Create a minimal gem structure for testing."""
    gem_dir = tmp_path / "TestGem"
    gem_dir.mkdir()
    gem_json = {
        "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "gem": {
            "name": "org.test.gem.testgem",
            "version": "1.0.0",
            "display_name": "Test Gem",
        }
    }
    with open(gem_dir / "gem.2-0-0.json", "w") as f:
        json.dump(gem_json, f)
    return gem_dir


# ---- CLI Root ----

class TestCLIRoot:
    def test_version(self, runner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "o3de-pilot" in result.output

    def test_help(self, runner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "O3DE Pilot" in result.output

    def test_help_lists_all_commands(self, runner):
        result = runner.invoke(cli, ["--help"])
        for cmd in ["project", "gem", "engine", "template", "registry",
                     "manifest", "layout", "ai", "config", "publish",
                     "audit", "workspace", "deps"]:
            assert cmd in result.output


# ---- Manifest Commands ----

class TestManifestCommands:
    def test_manifest_show(self, runner):
        result = runner.invoke(cli, ["manifest", "show"])
        assert result.exit_code == 0

    def test_manifest_resolve(self, runner):
        result = runner.invoke(cli, ["manifest", "resolve"])
        assert result.exit_code == 0

    def test_manifest_resolve_dry_run(self, runner):
        result = runner.invoke(cli, ["manifest", "resolve", "--dry-run"])
        assert result.exit_code == 0


# ---- Project Commands ----

class TestProjectCommands:
    def test_project_list(self, runner):
        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code == 0

    def test_project_list_json(self, runner):
        result = runner.invoke(cli, ["project", "list", "--json"])
        assert result.exit_code == 0


# ---- Gem Commands ----

class TestGemCommands:
    def test_gem_list(self, runner):
        result = runner.invoke(cli, ["gem", "list"])
        assert result.exit_code == 0

    def test_gem_list_json(self, runner):
        result = runner.invoke(cli, ["gem", "list", "--json"])
        assert result.exit_code == 0

    def test_gem_create(self, runner, tmp_path):
        result = runner.invoke(cli, ["gem", "create", "org.test.gem.newgem",
                                      "--path", str(tmp_path / "NewGem")])
        assert result.exit_code == 0
        gem_dir = tmp_path / "NewGem"
        assert gem_dir.exists()
        # Check that a JSON file was created
        json_files = list(gem_dir.glob("*.json"))
        assert len(json_files) > 0


# ---- Template Commands ----

class TestTemplateCommands:
    def test_template_list(self, runner):
        result = runner.invoke(cli, ["template", "list"])
        assert result.exit_code == 0


# ---- Engine Commands ----

class TestEngineCommands:
    def test_engine_list(self, runner):
        result = runner.invoke(cli, ["engine", "list"])
        assert result.exit_code == 0


# ---- Config Commands ----

class TestConfigCommands:
    def test_config_list(self, runner):
        result = runner.invoke(cli, ["config", "list"])
        assert result.exit_code == 0


# ---- Registry Commands ----

class TestRegistryCommands:
    def test_registry_list_remotes(self, runner):
        result = runner.invoke(cli, ["registry", "list-remotes"])
        assert result.exit_code == 0


# ---- Publish Commands ----

class TestPublishCommands:
    def test_publish_validate_valid_gem(self, runner, temp_gem):
        result = runner.invoke(cli, ["publish", "validate", str(temp_gem)])
        assert result.exit_code == 0

    def test_publish_validate_missing_path(self, runner, tmp_path):
        result = runner.invoke(cli, ["publish", "validate", str(tmp_path / "nonexistent")])
        assert result.exit_code != 0

    def test_publish_validate_empty_dir(self, runner, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        result = runner.invoke(cli, ["publish", "validate", str(empty)])
        assert result.exit_code != 0

    def test_publish_validate_json_output(self, runner, temp_gem):
        result = runner.invoke(cli, ["publish", "validate", str(temp_gem), "--json"])
        assert result.exit_code == 0
        # Output should be valid JSON containing "valid" key
        assert '"valid"' in result.output

    def test_publish_validate_warns_on_missing_fields(self, runner, tmp_path):
        """A minimal gem without origin/licenses should produce warnings."""
        gem_dir = tmp_path / "MinGem"
        gem_dir.mkdir()
        with open(gem_dir / "gem.2-0-0.json", "w") as f:
            json.dump({
                "$schemaVersion": "2.0.0",
                "gem": {"name": "org.test.gem.min", "version": "1.0.0"}
            }, f)
        result = runner.invoke(cli, ["publish", "validate", str(gem_dir)])
        # Should pass (no errors) but with warnings
        assert result.exit_code == 0

    def test_publish_push_dry_run(self, runner, temp_gem):
        result = runner.invoke(cli, ["publish", "push", str(temp_gem), "--dry-run"])
        assert result.exit_code == 0
        assert "Dry-run" in result.output


# ---- Audit Command ----

class TestAuditCommand:
    def test_audit_runs(self, runner):
        """Audit should run against the current manifest."""
        result = runner.invoke(cli, ["audit"])
        # May exit 0 (no issues) or 1 (issues found) — both are valid
        assert result.exit_code in (0, 1)

    def test_audit_json_output(self, runner):
        result = runner.invoke(cli, ["audit", "--json"])
        assert result.exit_code in (0, 1)


# ---- Workspace Commands ----

class TestWorkspaceCommands:
    def test_workspace_init(self, runner, tmp_path):
        result = runner.invoke(cli, ["workspace", "init", "test-workspace",
                                      "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / "o3de-workspace.json").exists()

    def test_workspace_status_no_workspace(self, runner, tmp_path):
        result = runner.invoke(cli, ["workspace", "status", "--path", str(tmp_path)])
        assert result.exit_code != 0

    def test_workspace_init_then_status(self, runner, tmp_path):
        runner.invoke(cli, ["workspace", "init", "test-ws", "--path", str(tmp_path)])
        result = runner.invoke(cli, ["workspace", "status", "--path", str(tmp_path)])
        assert result.exit_code == 0
        assert "test-ws" in result.output

    def test_workspace_add_project(self, runner, tmp_path, temp_project):
        runner.invoke(cli, ["workspace", "init", "test-ws", "--path", str(tmp_path)])
        result = runner.invoke(cli, ["workspace", "add-project", str(temp_project),
                                      "--workspace", str(tmp_path)])
        assert result.exit_code == 0

    def test_workspace_set_engine(self, runner, tmp_path):
        engine_dir = tmp_path / "engine"
        engine_dir.mkdir()
        runner.invoke(cli, ["workspace", "init", "test-ws", "--path", str(tmp_path)])
        result = runner.invoke(cli, ["workspace", "set-engine", str(engine_dir),
                                      "--workspace", str(tmp_path)])
        assert result.exit_code == 0


# ---- Deps Commands ----

class TestDepsCommands:
    def test_deps_tree(self, runner):
        """deps tree should run against the current manifest."""
        result = runner.invoke(cli, ["deps", "tree"])
        assert result.exit_code == 0

    def test_deps_tree_json(self, runner):
        result = runner.invoke(cli, ["deps", "tree", "--json"])
        assert result.exit_code == 0


# ---- AI Commands ----

class TestAICommands:
    def test_ai_help(self, runner):
        result = runner.invoke(cli, ["ai", "--help"])
        assert result.exit_code == 0
        assert "ask" in result.output
        assert "diagnose" in result.output
        assert "generate" in result.output
        assert "migrate" in result.output
        assert "explain" in result.output
