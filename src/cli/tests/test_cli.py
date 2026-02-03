# O3DE Pilot CLI - CLI Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for CLI commands."""

from click.testing import CliRunner
from o3de_pilot.__main__ import cli


def test_cli_version():
    """Test that --version works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "o3de-pilot" in result.output


def test_cli_help():
    """Test that --help works."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "O3DE Pilot" in result.output


def test_project_list():
    """Test project list command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["project", "list"])
    # Should work even with no projects
    assert result.exit_code == 0


def test_gem_list():
    """Test gem list command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["gem", "list"])
    assert result.exit_code == 0


def test_config_list():
    """Test config list command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["config", "list"])
    assert result.exit_code == 0
