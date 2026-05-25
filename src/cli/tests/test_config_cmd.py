# O3DE Pilot - Config & Misc Command Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for config command and other remaining branches."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner


class TestConfigGet:
    def test_get_all(self):
        from o3de_pilot.commands.config import config
        mock_cfg = MagicMock()
        mock_cfg.all.return_value = {"ai.provider": "ollama", "ai.model": "llama3"}
        runner = CliRunner()
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            result = runner.invoke(config, ["get"])
        assert result.exit_code == 0

    def test_get_specific(self):
        from o3de_pilot.commands.config import config
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = "ollama"
        runner = CliRunner()
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            result = runner.invoke(config, ["get", "ai.provider"])
        assert result.exit_code == 0
        assert "ollama" in result.output

    def test_get_not_found(self):
        from o3de_pilot.commands.config import config
        mock_cfg = MagicMock()
        mock_cfg.get.return_value = None
        runner = CliRunner()
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            result = runner.invoke(config, ["get", "nope"])
        assert "not found" in result.output.lower()


class TestConfigSet:
    def test_set(self):
        from o3de_pilot.commands.config import config
        mock_cfg = MagicMock()
        runner = CliRunner()
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            result = runner.invoke(config, ["set", "ai.provider", "claude"])
        assert result.exit_code == 0
        mock_cfg.set.assert_called_once_with("ai.provider", "claude")
        mock_cfg.save.assert_called_once()


class TestConfigUnset:
    def test_unset(self):
        from o3de_pilot.commands.config import config
        mock_cfg = MagicMock()
        runner = CliRunner()
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            result = runner.invoke(config, ["unset", "ai.provider"])
        assert result.exit_code == 0
        mock_cfg.unset.assert_called_once_with("ai.provider")


class TestConfigList:
    def test_list(self):
        from o3de_pilot.commands.config import config
        mock_cfg = MagicMock()
        mock_cfg.all.return_value = {"ai.provider": "ollama", "ai.api_key": "secret123"}
        runner = CliRunner()
        with patch("o3de_pilot.core.config.get_config", return_value=mock_cfg):
            result = runner.invoke(config, ["list"])
        assert result.exit_code == 0
        # api_key should be masked
        assert "secret123" not in result.output


class TestConfigPath:
    def test_path(self):
        from o3de_pilot.commands.config import config
        runner = CliRunner()
        with patch("o3de_pilot.core.config.get_config_path",
                    return_value=Path("/home/test/.config/o3de-pilot/config.yaml")):
            result = runner.invoke(config, ["path"])
        assert result.exit_code == 0
        assert "config" in result.output.lower()
