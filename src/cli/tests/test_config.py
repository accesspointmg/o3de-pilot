# O3DE Pilot - Config Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.config module."""

import pytest
import tempfile
from pathlib import Path

from o3de_pilot.core.config import Config


class TestConfigInit:
    """Test Config initialization."""

    def test_default_init(self):
        """Config should initialize with defaults when no file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            cfg = Config(path=config_path)
            assert cfg._data is not None
            assert isinstance(cfg._data, dict)

    def test_load_existing_file(self):
        """Should load from existing YAML file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("ai:\n  provider: openai\n")
            cfg = Config(path=config_path)
            assert cfg.get("ai.provider") == "openai"


class TestConfigGetSet:
    """Test Config get/set operations."""

    def test_get_existing_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(path=Path(tmpdir) / "config.yaml")
            cfg.set("test.key", "value")
            assert cfg.get("test.key") == "value"

    def test_get_missing_key_returns_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(path=Path(tmpdir) / "config.yaml")
            assert cfg.get("nonexistent.key") is None
            assert cfg.get("nonexistent.key", "fallback") == "fallback"

    def test_set_nested_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(path=Path(tmpdir) / "config.yaml")
            cfg.set("a.b.c", 42)
            assert cfg.get("a.b.c") == 42

    def test_set_overwrites(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(path=Path(tmpdir) / "config.yaml")
            cfg.set("key", "old")
            cfg.set("key", "new")
            assert cfg.get("key") == "new"


class TestConfigUnset:
    """Test Config unset operation."""

    def test_unset_existing_key(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(path=Path(tmpdir) / "config.yaml")
            cfg.set("test.key", "value")
            cfg.unset("test.key")
            assert cfg.get("test.key") is None

    def test_unset_nonexistent_key(self):
        """Should not raise when unsetting non-existent key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(path=Path(tmpdir) / "config.yaml")
            cfg.unset("nonexistent.key")  # Should not raise


class TestConfigAll:
    """Test Config.all() flattening."""

    def test_all_returns_flat_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = Config(path=Path(tmpdir) / "config.yaml")
            cfg.set("a.b", 1)
            cfg.set("a.c", 2)
            cfg.set("d", 3)
            result = cfg.all()
            assert result["a.b"] == 1
            assert result["a.c"] == 2
            assert result["d"] == 3

    def test_all_empty_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            config_path.write_text("{}\n")
            cfg = Config(path=config_path)
            result = cfg.all()
            assert isinstance(result, dict)


class TestConfigSave:
    """Test Config persistence."""

    def test_save_and_reload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.yaml"
            cfg1 = Config(path=config_path)
            cfg1.set("test.key", "saved_value")
            cfg1.save()

            cfg2 = Config(path=config_path)
            assert cfg2.get("test.key") == "saved_value"

    def test_save_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "subdir" / "deep" / "config.yaml"
            cfg = Config(path=config_path)
            cfg.set("key", "val")
            cfg.save()
            assert config_path.exists()
