# O3DE Pilot - AI Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for the ai CLI command group."""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner


class TestAIAsk:
    def test_ask_success(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "The answer is 42."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["ask", "what", "is", "O3DE"])
        assert result.exit_code == 0
        assert "42" in result.output

    def test_ask_error(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        with patch("o3de_cli.ai.provider.get_ai_provider", side_effect=ValueError("no key")):
            result = runner.invoke(ai, ["ask", "hello"])
        assert "AI Error" in result.output or "no key" in result.output

    def test_ask_provider_error(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.side_effect = RuntimeError("connection failed")
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["ask", "hello"])
        assert "Error" in result.output


class TestAIDiagnose:
    def test_diagnose_no_logs(self, tmp_path):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "No errors found."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["diagnose", "--path", str(tmp_path)])
        assert result.exit_code == 0
        mock_provider.complete.assert_called_once()

    def test_diagnose_with_build_log(self, tmp_path):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        build_dir = tmp_path / "build"
        build_dir.mkdir()
        (build_dir / "CMakeError.log").write_text("error: missing target")
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Missing target dependency."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["diagnose", "--path", str(tmp_path)])
        assert result.exit_code == 0
        prompt = mock_provider.complete.call_args[0][0]
        assert "CMakeError.log" in prompt


class TestAIGenerate:
    def test_generate_gem(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "# MyGem\nGenerated gem code."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["generate", "gem", "physics", "simulation"])
        assert result.exit_code == 0
        prompt = mock_provider.complete.call_args[0][0]
        assert "gem" in prompt
        assert "physics simulation" in prompt

    def test_generate_component(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Generated component."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["generate", "component", "health", "bar"])
        assert result.exit_code == 0

    def test_generate_script(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Generated script."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["generate", "script", "player", "movement"])
        assert result.exit_code == 0

    def test_generate_invalid_type(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        result = runner.invoke(ai, ["generate", "invalid", "thing"])
        assert result.exit_code != 0


class TestAIMigrate:
    def test_migrate_no_project(self, tmp_path):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "No project files found."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["migrate", "--path", str(tmp_path)])
        assert result.exit_code == 0
        mock_provider.complete.assert_called_once()

    def test_migrate_with_project_json(self, tmp_path):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        (tmp_path / "project.json").write_text('{"project_name": "TestProject"}')
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Update project.json schema."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["migrate", "--path", str(tmp_path), "--target", "24.09"])
        assert result.exit_code == 0
        prompt = mock_provider.complete.call_args[0][0]
        assert "project.json" in prompt
        assert "24.09" in prompt


class TestAIExplain:
    def test_explain_topic(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_provider = MagicMock()
        mock_provider.complete.return_value = "Gems are modular packages."
        with patch("o3de_cli.ai.provider.get_ai_provider", return_value=mock_provider):
            result = runner.invoke(ai, ["explain", "gems", "and", "components"])
        assert result.exit_code == 0
        prompt = mock_provider.complete.call_args[0][0]
        assert "gems and components" in prompt


class TestAIModels:
    def test_models_json_output(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda k, d="": {
            "ai.provider": "anthropic",
            "ai.api_key": "sk-test",
            "ai.api_keys": {},
            "ai.ollama_url": "http://localhost:11434",
        }.get(k, d)
        with patch("o3de_cli.core.config.get_config", return_value=mock_cfg), \
             patch("o3de_cli.ai.provider.discover_models", return_value=[
                 {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4"},
             ]):
            result = runner.invoke(ai, ["models", "--json"])
        assert result.exit_code == 0
        import json
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "claude-sonnet-4-20250514"

    def test_models_no_results(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda k, d="": {
            "ai.provider": "anthropic",
            "ai.api_key": "",
            "ai.api_keys": {},
            "ai.ollama_url": "",
        }.get(k, d)
        with patch("o3de_cli.core.config.get_config", return_value=mock_cfg), \
             patch("o3de_cli.ai.provider.discover_models", return_value=[]):
            result = runner.invoke(ai, ["models"])
        assert result.exit_code == 0
        assert "No models" in result.output

    def test_models_table_output(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_cfg = MagicMock()
        mock_cfg.get.side_effect = lambda k, d="": {
            "ai.provider": "ollama",
            "ai.api_key": "",
            "ai.api_keys": {},
            "ai.ollama_url": "http://localhost:11434",
        }.get(k, d)
        with patch("o3de_cli.core.config.get_config", return_value=mock_cfg), \
             patch("o3de_cli.ai.provider.discover_models", return_value=[
                 {"id": "llama3", "name": "llama3", "size": 4_000_000_000},
             ]):
            result = runner.invoke(ai, ["models"])
        assert result.exit_code == 0
        assert "llama3" in result.output
        assert "1 model(s)" in result.output


class TestThinkingCLI:
    """Tests for --thinking flag on CLI commands."""

    def _mock_cfg(self, extra=None):
        cfg = {
            "ai.enabled": "true",
            "ai.provider": "ollama",
            "ai.model": "llama3",
            "ai.api_key": "",
            "ai.ollama_url": "http://localhost:11434",
        }
        if extra:
            cfg.update(extra)
        mock = MagicMock()
        mock.get = lambda k, d=None: cfg.get(k, d)
        return mock

    def test_ask_thinking_flag(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        with patch("o3de_cli.core.config.get_config", return_value=self._mock_cfg()), \
             patch("o3de_cli.ai.provider.OllamaProvider.complete", return_value="answer") as mock_complete:
            result = runner.invoke(ai, ["ask", "--thinking", "high", "test"])
        assert result.exit_code == 0

    def test_status_shows_thinking(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        with patch("o3de_cli.core.config.get_config",
                    return_value=self._mock_cfg({"ai.thinking_effort": "medium"})):
            result = runner.invoke(ai, ["status"])
        assert result.exit_code == 0
        assert "medium" in result.output


class TestAILocal:
    """Tests for `ai local` command."""

    def _mock_cfg(self):
        cfg = {}
        mock = MagicMock()
        mock.get = lambda k, d=None: cfg.get(k, d)
        return mock

    def test_local_ollama_not_running(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        with patch("o3de_cli.core.config.get_config", return_value=self._mock_cfg()), \
             patch("o3de_cli.ai.provider._ollama_is_running", return_value=False):
            result = runner.invoke(ai, ["local"])
        assert result.exit_code != 0
        assert "not running" in result.output

    def test_local_model_already_available(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_cfg = self._mock_cfg()
        with patch("o3de_cli.core.config.get_config", return_value=mock_cfg), \
             patch("o3de_cli.ai.provider._ollama_is_running", return_value=True), \
             patch("o3de_cli.ai.provider._ollama_has_model", return_value=True):
            result = runner.invoke(ai, ["local"])
        assert result.exit_code == 0
        assert "already available" in result.output

    def test_local_pulls_model(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_cfg = self._mock_cfg()
        with patch("o3de_cli.core.config.get_config", return_value=mock_cfg), \
             patch("o3de_cli.ai.provider._ollama_is_running", return_value=True), \
             patch("o3de_cli.ai.provider._ollama_has_model", return_value=False), \
             patch("o3de_cli.ai.provider._ollama_pull", return_value=True):
            result = runner.invoke(ai, ["local"])
        assert result.exit_code == 0
        assert "pulled successfully" in result.output

    def test_local_custom_model(self):
        from o3de_pilot_gui.ai.commands import ai
        runner = CliRunner()
        mock_cfg = self._mock_cfg()
        with patch("o3de_cli.core.config.get_config", return_value=mock_cfg), \
             patch("o3de_cli.ai.provider._ollama_is_running", return_value=True), \
             patch("o3de_cli.ai.provider._ollama_has_model", return_value=True):
            result = runner.invoke(ai, ["local", "--model", "codellama:7b"])
        assert result.exit_code == 0
