# O3DE Pilot - AI Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for the ai CLI command group."""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner


class TestAIAsk:
    def test_ask_success(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "The answer is 42."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["ask", "what", "is", "O3DE"])
        assert result.exit_code == 0
        assert "42" in result.output

    def test_ask_error(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        with patch("o3de_pilot.ai.provider.get_ai_provider", side_effect=ValueError("no key")):
            result = runner.invoke(ai, ["ask", "hello"])
        assert "AI Error" in result.output or "no key" in result.output

    def test_ask_provider_error(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.side_effect = RuntimeError("connection failed")
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["ask", "hello"])
        assert "Error" in result.output


class TestAIDiagnose:
    def test_diagnose_no_logs(self, tmp_path):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "No errors found."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["diagnose", "--path", str(tmp_path)])
        assert result.exit_code == 0
        mock_provider.complete.assert_called_once()

    def test_diagnose_with_build_log(self, tmp_path):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "CMakeError.log").write_text("error: missing target")
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Missing target dependency."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["diagnose", "--path", str(tmp_path)])
        assert result.exit_code == 0
        prompt = mock_provider.complete.call_args[0][0]
        assert "CMakeError.log" in prompt


class TestAIGenerate:
    def test_generate_gem(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "# MyGem\nGenerated gem code."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["generate", "gem", "physics", "simulation"])
        assert result.exit_code == 0
        prompt = mock_provider.complete.call_args[0][0]
        assert "gem" in prompt
        assert "physics simulation" in prompt

    def test_generate_component(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Generated component."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["generate", "component", "health", "bar"])
        assert result.exit_code == 0

    def test_generate_script(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Generated script."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["generate", "script", "player", "movement"])
        assert result.exit_code == 0

    def test_generate_invalid_type(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["generate", "invalid", "thing"])
        assert result.exit_code != 0


class TestAIMigrate:
    def test_migrate_no_project(self, tmp_path):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "No project files found."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["migrate", "--path", str(tmp_path)])
        assert result.exit_code == 0
        mock_provider.complete.assert_called_once()

    def test_migrate_with_project_json(self, tmp_path):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        (tmp_path / "project.json").write_text('{"project_name": "TestProject"}')
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Update project.json schema."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["migrate", "--path", str(tmp_path), "--target", "24.09"])
        assert result.exit_code == 0
        prompt = mock_provider.complete.call_args[0][0]
        assert "project.json" in prompt
        assert "24.09" in prompt


class TestAIExplain:
    def test_explain_topic(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Gems are modular packages."
        with patch("o3de_pilot.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["explain", "gems", "and", "components"])
        assert result.exit_code == 0
        prompt = mock_provider.complete.call_args[0][0]
        assert "gems and components" in prompt
