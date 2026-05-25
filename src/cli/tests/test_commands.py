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
                     "manifest", "workspace", "ai", "config", "publish",
                     "audit", "deps"]:
            assert cmd in result.output


# ---- Manifest Commands ----

class TestManifestCommands:
    def test_manifest_show(self, runner, mock_manifest):
        result = runner.invoke(cli, ["manifest", "show"])
        assert result.exit_code == 0
        assert "test" in result.output  # manifest name from fixture

    def test_manifest_resolve(self, runner, mock_manifest, tmp_path):
        result = runner.invoke(cli, ["manifest", "resolve"])
        assert result.exit_code == 0
        # Resolved manifest should be written
        resolved = tmp_path / "resolved_o3de_manifest.json"
        assert resolved.exists()

    def test_manifest_resolve_dry_run(self, runner, mock_manifest, tmp_path):
        result = runner.invoke(cli, ["manifest", "resolve", "--dry-run"])
        assert result.exit_code == 0
        # Resolved manifest should NOT be written in dry-run mode
        resolved = tmp_path / "resolved_o3de_manifest.json"
        assert not resolved.exists()


# ---- Project Commands ----

class TestProjectCommands:
    def test_project_list(self, runner, mock_manifest, tmp_path):
        import json as _json
        from tests.conftest import _write_json
        proj_dir = tmp_path / "Proj1"
        proj_dir.mkdir()
        _write_json(proj_dir / "project.2-0-0.json", {
            "$schema": "https://overlo3de.com/o3de-project-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "project": {"name": "org.test.project.proj1", "version": "1.0.0",
                         "display_name": "Proj1"},
        })
        manifest_data = _json.loads(mock_manifest.read_text())
        manifest_data.setdefault("local", {}).setdefault("projects", []).append(proj_dir.as_posix())
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["project", "list"])
        assert result.exit_code == 0
        assert "org.test.project.proj1" in result.output

    def test_project_list_json(self, runner, mock_manifest, tmp_path):
        import json as _json
        from tests.conftest import _write_json
        proj_dir = tmp_path / "Proj1"
        proj_dir.mkdir()
        _write_json(proj_dir / "project.2-0-0.json", {
            "$schema": "https://overlo3de.com/o3de-project-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "project": {"name": "org.test.project.proj1", "version": "1.0.0",
                         "display_name": "Proj1"},
        })
        manifest_data = _json.loads(mock_manifest.read_text())
        manifest_data.setdefault("local", {}).setdefault("projects", []).append(proj_dir.as_posix())
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["project", "list", "--json"])
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "org.test.project.proj1"


# ---- Gem Commands ----

class TestGemCommands:
    def test_gem_list(self, runner, mock_manifest, tmp_path):
        import json as _json
        from tests.conftest import make_gem
        gem_dir = make_gem(tmp_path, "org.test.gem.alpha", "2.0.0")
        manifest_data = _json.loads(mock_manifest.read_text())
        manifest_data.setdefault("local", {}).setdefault("gems", []).append(gem_dir.as_posix())
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["gem", "list"])
        assert result.exit_code == 0
        assert "org.test.gem.alpha" in result.output

    def test_gem_list_json(self, runner, mock_manifest, tmp_path):
        import json as _json
        from tests.conftest import make_gem
        gem_dir = make_gem(tmp_path, "org.test.gem.alpha", "2.0.0")
        manifest_data = _json.loads(mock_manifest.read_text())
        manifest_data.setdefault("local", {}).setdefault("gems", []).append(gem_dir.as_posix())
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["gem", "list", "--json"])
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["name"] == "org.test.gem.alpha"

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
    def test_template_list(self, runner, mock_manifest, tmp_path):
        import json as _json
        from tests.conftest import _write_json
        tpl_dir = tmp_path / "Tpl1"
        tpl_dir.mkdir()
        _write_json(tpl_dir / "template.2-0-0.json", {
            "$schema": "https://overlo3de.com/o3de-template-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "template": {"name": "org.test.template.tpl1", "version": "1.0.0",
                          "display_name": "Tpl1"},
        })
        manifest_data = _json.loads(mock_manifest.read_text())
        manifest_data.setdefault("local", {}).setdefault("templates", []).append(tpl_dir.as_posix())
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["template", "list"])
        assert result.exit_code == 0
        assert "org.test.template.tpl1" in result.output


# ---- Engine Commands ----

class TestEngineCommands:
    def test_engine_list(self, runner, mock_manifest, tmp_path):
        import json as _json
        from tests.conftest import _write_json
        eng_dir = tmp_path / "Eng1"
        eng_dir.mkdir()
        _write_json(eng_dir / "engine.2-0-0.json", {
            "$schema": "https://overlo3de.com/o3de-engine-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "engine": {"name": "org.test.engine.eng1", "version": "1.0.0",
                        "display_name": "Eng1"},
        })
        manifest_data = _json.loads(mock_manifest.read_text())
        manifest_data.setdefault("local", {}).setdefault("engines", []).append(eng_dir.as_posix())
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["engine", "list"])
        assert result.exit_code == 0
        assert "org.test.engine.eng1" in result.output


# ---- Config Commands ----

class TestConfigCommands:
    def test_config_list(self, runner, mock_manifest):
        result = runner.invoke(cli, ["config", "list"])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0


# ---- Registry Commands ----

class TestRegistryCommands:
    def test_registry_list_remotes(self, runner, mock_manifest):
        import json as _json
        manifest_data = _json.loads(mock_manifest.read_text())
        manifest_data["remotes"] = ["https://example.com/repo.json"]
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["registry", "list-remotes"])
        assert result.exit_code == 0
        assert "example.com" in result.output


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
        data = json.loads(result.output)
        assert "valid" in data
        assert data["valid"] is True

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
        assert result.exit_code == 0
        # Should have warnings about missing fields
        output_lower = result.output.lower()
        assert "warning" in output_lower or "origin" in output_lower or "license" in output_lower

    def test_publish_push_dry_run(self, runner, temp_gem):
        result = runner.invoke(cli, ["publish", "push", str(temp_gem), "--dry-run"])
        assert result.exit_code == 0
        assert "Dry-run" in result.output


# ---- Audit Command ----

class TestAuditCommand:
    def test_audit_runs(self, runner, mock_manifest):
        """Audit should run against the fixture manifest with deterministic results."""
        result = runner.invoke(cli, ["audit"])
        assert result.exit_code in (0, 1)

    def test_audit_json_output(self, runner, mock_manifest):
        result = runner.invoke(cli, ["audit", "--json"])
        assert result.exit_code in (0, 1)
        import json as _json
        data = _json.loads(result.output)
        assert isinstance(data, (list, dict))


# ---- Workspace Commands (symlinked build directories) ----

class TestWorkspaceCommands:
    def test_workspace_help(self, runner):
        result = runner.invoke(cli, ["workspace", "--help"])
        assert result.exit_code == 0
        assert "create" in result.output
        assert "list" in result.output

    def test_workspace_list(self, runner, mock_manifest):
        result = runner.invoke(cli, ["workspace", "list"])
        assert result.exit_code == 0

    def test_workspace_create_missing_args(self, runner):
        """Create without required args should fail."""
        result = runner.invoke(cli, ["workspace", "create"])
        assert result.exit_code != 0


# ---- Deps Commands ----

class TestDepsCommands:
    def test_deps_tree(self, runner, mock_manifest, tmp_path):
        """deps tree should show dependency edges."""
        import json as _json
        from tests.conftest import make_gem
        gem_a = make_gem(tmp_path, "org.test.gem.a", "1.0.0", deps=["org.test.gem.b"])
        gem_b = make_gem(tmp_path, "org.test.gem.b", "1.0.0")
        manifest_data = _json.loads(mock_manifest.read_text())
        local = manifest_data.setdefault("local", {})
        local.setdefault("gems", []).extend([gem_a.as_posix(), gem_b.as_posix()])
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["deps", "tree"])
        assert result.exit_code == 0
        assert "org.test.gem.a" in result.output

    def test_deps_tree_json(self, runner, mock_manifest, tmp_path):
        import json as _json
        from tests.conftest import make_gem
        gem_a = make_gem(tmp_path, "org.test.gem.a", "1.0.0")
        manifest_data = _json.loads(mock_manifest.read_text())
        manifest_data.setdefault("local", {}).setdefault("gems", []).append(gem_a.as_posix())
        mock_manifest.write_text(_json.dumps(manifest_data))
        result = runner.invoke(cli, ["deps", "tree", "--json"])
        assert result.exit_code == 0
        data = _json.loads(result.output)
        assert isinstance(data, (list, dict))


# ---- AI Commands ----

class TestAICommands:
    def test_ai_help(self, runner):
        result = runner.invoke(cli, ["ai", "--help"])
        assert result.exit_code == 0
        for subcmd in ["ask", "diagnose", "generate", "migrate", "explain"]:
            assert subcmd in result.output, f"Missing AI subcommand: {subcmd}"


# ---- Deep Behavioral Integration Tests ----

class TestManifestAddRemoveRoundTrip:
    """Test that adding then removing an object works end-to-end."""

    def test_add_then_remove_gem(self, runner, temp_gem, tmp_path):
        """manifest add → show → remove → show should round-trip cleanly."""
        manifest = tmp_path / "o3de_manifest.json"
        manifest.write_text(json.dumps({
            "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "o3de_manifest": {"name": "test"},
            "local": {"engines": [], "gems": [], "projects": [], "templates": []}
        }))

        from unittest.mock import patch
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=manifest):
            # Add
            result = runner.invoke(cli, ["manifest", "add", str(temp_gem)])
            assert result.exit_code == 0
            assert "Added" in result.output

            # Verify it's in the manifest
            data = json.loads(manifest.read_text())
            assert len(data["local"]["gems"]) == 1

            # Add again should say already registered
            result = runner.invoke(cli, ["manifest", "add", str(temp_gem)])
            assert result.exit_code == 0
            assert "Already" in result.output

            # Remove
            result = runner.invoke(cli, ["manifest", "remove", str(temp_gem)])
            assert result.exit_code == 0
            assert "Removed" in result.output

            # Verify it's gone
            data = json.loads(manifest.read_text())
            assert len(data["local"]["gems"]) == 0

    def test_remove_nonexistent_warns(self, runner, tmp_path):
        """Removing a path not in manifest should warn."""
        manifest = tmp_path / "o3de_manifest.json"
        manifest.write_text(json.dumps({
            "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "o3de_manifest": {"name": "test"},
            "local": {"gems": []}
        }))

        from unittest.mock import patch
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=manifest):
            result = runner.invoke(cli, ["manifest", "remove", str(tmp_path / "no_such_gem")])
            assert result.exit_code == 0
            assert "Not found" in result.output


class TestResolveWithDependencies:
    """Test that resolve correctly handles dependency graphs."""

    def test_resolve_reports_missing_deps(self, runner, tmp_path):
        """Resolving a manifest with missing deps should report them."""
        # Create a gem that depends on a non-existent gem
        gem_dir = tmp_path / "GemA"
        gem_dir.mkdir()
        with open(gem_dir / "gem.2-0-0.json", "w") as f:
            json.dump({
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {
                    "name": "org.test.gem.a",
                    "version": "1.0.0",
                },
                "dependent": {"gems": ["org.test.gem.missing"]},
            }, f)

        manifest = tmp_path / "o3de_manifest.json"
        manifest.write_text(json.dumps({
            "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "o3de_manifest": {"name": "test"},
            "local": {"gems": [gem_dir.as_posix()]}
        }))

        from unittest.mock import patch
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=manifest), \
             patch("o3de_pilot.commands.manifest.get_resolved_manifest_path", return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=manifest), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path", return_value=tmp_path / "resolved.json"):
                result = runner.invoke(cli, ["manifest", "resolve"])
                assert result.exit_code == 0
                assert "Missing" in result.output or "missing" in result.output.lower()

    def test_resolve_satisfied_deps(self, runner, tmp_path):
        """Resolving with all deps present should succeed without warnings."""
        gem_a = tmp_path / "GemA"
        gem_a.mkdir()
        with open(gem_a / "gem.2-0-0.json", "w") as f:
            json.dump({
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {"name": "org.test.gem.a", "version": "1.0.0"},
                "dependent": {"gems": ["org.test.gem.b"]},
            }, f)

        gem_b = tmp_path / "GemB"
        gem_b.mkdir()
        with open(gem_b / "gem.2-0-0.json", "w") as f:
            json.dump({
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {"name": "org.test.gem.b", "version": "2.0.0"},
            }, f)

        manifest = tmp_path / "o3de_manifest.json"
        manifest.write_text(json.dumps({
            "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "o3de_manifest": {"name": "test"},
            "local": {"gems": [gem_a.as_posix(), gem_b.as_posix()]}
        }))

        from unittest.mock import patch
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=manifest), \
             patch("o3de_pilot.commands.manifest.get_resolved_manifest_path", return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=manifest), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path", return_value=tmp_path / "resolved.json"):
                result = runner.invoke(cli, ["manifest", "resolve"])
                assert result.exit_code == 0
                assert "Missing" not in result.output

                # Verify resolved manifest was written
                resolved = tmp_path / "resolved.json"
                assert resolved.exists()
                resolved_data = json.loads(resolved.read_text())
                assert "org.test.gem.a" in resolved_data.get("objects", {})
                assert "org.test.gem.b" in resolved_data.get("objects", {})


class TestPublishValidateBehavior:
    """Test publish validate catches real schema issues."""

    def test_invalid_version_format(self, runner, tmp_path):
        """Non-semver version should produce a warning."""
        gem_dir = tmp_path / "BadGem"
        gem_dir.mkdir()
        with open(gem_dir / "gem.2-0-0.json", "w") as f:
            json.dump({
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {"name": "org.test.gem.bad", "version": "not-semver"},
            }, f)
        result = runner.invoke(cli, ["publish", "validate", str(gem_dir)])
        assert "semver" in result.output.lower() or "version" in result.output.lower()

    def test_missing_type_header_errors(self, runner, tmp_path):
        """JSON without engine/gem/project key should error."""
        bad = tmp_path / "bad.json"
        bad.write_text('{"foo": "bar"}')
        result = runner.invoke(cli, ["publish", "validate", str(bad)])
        assert result.exit_code != 0

    def test_strict_mode_fails_on_warnings(self, runner, tmp_path):
        """--strict should fail if there are warnings."""
        gem_dir = tmp_path / "MinGem"
        gem_dir.mkdir()
        with open(gem_dir / "gem.2-0-0.json", "w") as f:
            json.dump({
                "$schemaVersion": "2.0.0",
                "gem": {"name": "org.test.gem.min", "version": "1.0.0"},
            }, f)
        result = runner.invoke(cli, ["publish", "validate", str(gem_dir), "--strict"])
        # Should fail because of missing origin/licenses warnings
        assert result.exit_code != 0

    def test_push_without_remote_fails(self, runner, tmp_path):
        """push without --remote and no manifest remote should fail."""
        gem_dir = tmp_path / "PushGem"
        gem_dir.mkdir()
        with open(gem_dir / "gem.2-0-0.json", "w") as f:
            json.dump({
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {"name": "org.test.gem.push", "version": "1.0.0"},
                "origin": {"name": "test", "url": "https://test.com"},
            }, f)

        from unittest.mock import patch
        # Mock schema validation to avoid canonical schema oneOf issues
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]), \
             patch("o3de_pilot.commands.publish.get_manifest_path",
                   return_value=tmp_path / "nonexistent_manifest.json"):
            result = runner.invoke(cli, ["publish", "push", str(gem_dir)])
            assert result.exit_code != 0
            assert "remote" in result.output.lower() or "No remote" in result.output


class TestGemCreateBehavior:
    """Test gem create produces valid structure."""

    def test_created_gem_validates(self, runner, tmp_path):
        """gem create → publish validate should pass."""
        result = runner.invoke(cli, ["gem", "create", "org.test.gem.newgem",
                                      "--path", str(tmp_path / "NewGem")])
        assert result.exit_code == 0

        result = runner.invoke(cli, ["publish", "validate", str(tmp_path / "NewGem")])
        assert result.exit_code == 0

    def test_created_gem_has_correct_name(self, runner, tmp_path):
        """gem create should set the correct name in the JSON."""
        gem_path = tmp_path / "MyGem"
        result = runner.invoke(cli, ["gem", "create", "org.test.gem.mygem",
                                      "--path", str(gem_path)])
        assert result.exit_code == 0

        # Find and parse the gem JSON
        json_files = list(gem_path.glob("*.json"))
        assert len(json_files) > 0
        with open(json_files[0]) as f:
            data = json.load(f)
        # Name should be set
        gem_data = data.get("gem", {})
        assert gem_data.get("name") == "org.test.gem.mygem"


class TestOptionalDependencies:
    """Test optional dependency reporting in resolve."""

    def test_optional_deps_surfaced(self, runner, tmp_path):
        """Resolve should mention missing optional deps without failing."""
        gem_a = tmp_path / "GemA"
        gem_a.mkdir()
        with open(gem_a / "gem.2-0-0.json", "w") as f:
            json.dump({
                "$schema": "https://overlo3de.com/o3de-gem-2.0.0.json",
                "$schemaVersion": "2.0.0",
                "gem": {"name": "org.test.gem.a", "version": "1.0.0"},
                "optional_dependent": {"gems": ["org.test.gem.optional"]},
            }, f)

        manifest = tmp_path / "o3de_manifest.json"
        manifest.write_text(json.dumps({
            "$schema": "https://overlo3de.com/o3de-manifest-2.0.0.json",
            "$schemaVersion": "2.0.0",
            "o3de_manifest": {"name": "test"},
            "local": {"gems": [gem_a.as_posix()]}
        }))

        from unittest.mock import patch
        with patch("o3de_pilot.commands.manifest.get_manifest_path", return_value=manifest), \
             patch("o3de_pilot.commands.manifest.get_resolved_manifest_path", return_value=tmp_path / "resolved.json"), \
             patch("o3de_pilot.core.resolver.get_manifest_path", return_value=manifest), \
             patch("o3de_pilot.core.resolver.get_resolved_manifest_path", return_value=tmp_path / "resolved.json"):
                result = runner.invoke(cli, ["manifest", "resolve"])
                assert result.exit_code == 0
                assert "optional" in result.output.lower() or "Optional" in result.output
