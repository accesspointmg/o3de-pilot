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
    def test_diagnose_not_implemented(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["diagnose"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output


class TestAIGenerate:
    def test_generate_gem(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["generate", "gem", "physics", "simulation"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output

    def test_generate_component(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["generate", "component", "health", "bar"])
        assert result.exit_code == 0

    def test_generate_script(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["generate", "script", "player", "movement"])
        assert result.exit_code == 0

    def test_generate_invalid_type(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["generate", "invalid", "thing"])
        assert result.exit_code != 0


class TestAIMigrate:
    def test_migrate_not_implemented(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["migrate"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output


class TestAIExplain:
    def test_explain_not_implemented(self):
        from o3de_pilot.commands.ai import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["explain", "gems", "and", "components"])
        assert result.exit_code == 0
        assert "not yet implemented" in result.output
