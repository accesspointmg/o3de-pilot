# O3DE Pilot - Publish Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for publish validate, pack, and push commands."""

import json
import tarfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from tests.conftest import _write_json


def _make_gem(tmp_path, name="org.test.gem.foo", version="1.0.0"):
    """Create a valid Schema 2.0 gem directory."""
    gdir = tmp_path / "mygem"
    gdir.mkdir(exist_ok=True)
    data = {
        "$schemaVersion": "2.0.0",
        "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
        "gem": {"name": name, "version": version},
        "origin": "test",
        "licenses": [{"name": "Apache-2.0"}],
    }
    _write_json(gdir / "gem.2-0-0.json", data)
    (gdir / "Code").mkdir()
    (gdir / "Code" / "main.cpp").write_text("// placeholder")
    return gdir


def _make_invalid_gem(tmp_path):
    """Create a gem missing required fields."""
    gdir = tmp_path / "badgem"
    gdir.mkdir(exist_ok=True)
    _write_json(gdir / "gem.2-0-0.json", {
        "$schemaVersion": "2.0.0",
        "gem": {"name": ""},  # missing version, empty name
    })
    return gdir


class TestPublishValidate:
    def test_validate_valid_gem(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["validate", str(gdir)])
        assert result.exit_code == 0

    def test_validate_invalid_gem(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_invalid_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["validate", str(gdir)])
        assert result.exit_code == 1

    def test_validate_json_output(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["validate", str(gdir), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["valid"] is True

    def test_validate_strict_fails_on_warnings(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = tmp_path / "warnobj"
        gdir.mkdir()
        # Missing origin and licenses → warnings
        _write_json(gdir / "gem.2-0-0.json", {
            "$schemaVersion": "2.0.0",
            "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
            "gem": {"name": "org.test.gem.x", "version": "1.0.0"},
        })
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["validate", str(gdir), "--strict"])
        assert result.exit_code == 1


class TestPublishPack:
    def test_pack_creates_tarball(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["pack", str(gdir)])
        assert result.exit_code == 0, f"Pack failed: {result.output}"
        # Check tarball was created
        archive = tmp_path / "org-test-gem-foo-1.0.0.tar.gz"
        assert archive.exists()
        # Verify it's a valid tarball
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            assert any("gem.2-0-0.json" in n for n in names)

    def test_pack_custom_output(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        out = tmp_path / "custom" / "my-gem.tar.gz"
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["pack", str(gdir), "-o", str(out)])
        assert result.exit_code == 0
        assert out.exists()

    def test_pack_json_output(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["pack", str(gdir), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
        assert data["data"]["name"] == "org.test.gem.foo"
        assert data["data"]["version"] == "1.0.0"
        assert data["data"]["sha256"]
        assert data["data"]["size_bytes"] > 0

    def test_pack_invalid_fails(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_invalid_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["pack", str(gdir)])
        assert result.exit_code == 1


class TestPublishPush:
    def test_push_dry_run(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["push", str(gdir), "--dry-run"])
        assert result.exit_code == 0
        assert "Dry-run" in result.output or "dry_run" in result.output

    def test_push_dry_run_json(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["push", str(gdir), "--dry-run", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["dry_run"] is True

    def test_push_to_local_repo(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        repo = tmp_path / "myrepo"
        repo.mkdir()
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, [
                "push", str(gdir), "--remote", str(repo),
            ])
        assert result.exit_code == 0, f"Push failed: {result.output}"
        # Check object was written to repo
        obj_json = repo / "gems" / "org-test-gem-foo" / "1.0.0" / "gem.2-0-0.json"
        assert obj_json.exists()
        # Check repo index was updated
        index = repo / "repo.2-0-0.json"
        assert index.exists()
        idx_data = json.loads(index.read_text())
        assert len(idx_data["gems"]) == 1

    def test_push_immutability_blocks_duplicate(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        repo = tmp_path / "myrepo"
        repo.mkdir()
        runner = CliRunner()

        # First push succeeds
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            r1 = runner.invoke(publish, ["push", str(gdir), "--remote", str(repo)])
        assert r1.exit_code == 0

        # Second push same version blocked by immutability
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            r2 = runner.invoke(publish, ["push", str(gdir), "--remote", str(repo)])
        assert r2.exit_code == 1
        assert "already exists" in r2.output

    def test_push_force_overrides_immutability(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        repo = tmp_path / "myrepo"
        repo.mkdir()
        runner = CliRunner()

        # First push
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            runner.invoke(publish, ["push", str(gdir), "--remote", str(repo)])

        # Force push succeeds
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            r2 = runner.invoke(publish, [
                "push", str(gdir), "--remote", str(repo), "--force",
            ])
        assert r2.exit_code == 0

    def test_push_no_remote_fails(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_gem(tmp_path)
        runner = CliRunner()
        # Patch manifest to have no remotes
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]), \
             patch("o3de_pilot.commands.publish.get_manifest_path",
                   return_value=tmp_path / "nonexistent.json"):
            result = runner.invoke(publish, ["push", str(gdir)])
        assert result.exit_code == 1

    def test_push_invalid_fails(self, tmp_path):
        from o3de_pilot.commands.publish import publish
        gdir = _make_invalid_gem(tmp_path)
        runner = CliRunner()
        with patch("o3de_pilot.commands.publish.validate_against_schema", return_value=[]):
            result = runner.invoke(publish, ["push", str(gdir), "--remote", "http://example.com"])
        assert result.exit_code == 1


class TestVersionImmutability:
    def test_local_repo_detects_existing_version(self, tmp_path):
        from o3de_pilot.commands.publish import _upload_local, _check_version_immutability
        from o3de_pilot.core import ObjectType

        repo = tmp_path / "repo"
        repo.mkdir()

        data = {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.gem.x", "version": "1.0.0"},
        }

        # First upload
        result = _upload_local(str(repo), data, ObjectType.GEM, "org.test.gem.x", "1.0.0")
        assert result.get("ok")

        # Check the file exists
        obj_json = repo / "gems" / "org-test-gem-x" / "1.0.0" / "gem.2-0-0.json"
        assert obj_json.exists()

    def test_repo_index_no_duplicate_on_rewrite(self, tmp_path):
        from o3de_pilot.commands.publish import _upload_local
        from o3de_pilot.core import ObjectType

        repo = tmp_path / "repo"
        repo.mkdir()

        data = {
            "$schemaVersion": "2.0.0",
            "gem": {"name": "org.test.gem.x", "version": "1.0.0"},
        }

        _upload_local(str(repo), data, ObjectType.GEM, "org.test.gem.x", "1.0.0")
        _upload_local(str(repo), data, ObjectType.GEM, "org.test.gem.x", "1.0.0")

        index = json.loads((repo / "repo.2-0-0.json").read_text())
        # Should not have duplicates
        assert len(index["gems"]) == 1
