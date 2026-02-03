# O3DE Pilot CLI - Configuration
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Configuration management for O3DE Pilot."""

from pathlib import Path
from typing import Any
import yaml

_config_instance: "Config | None" = None


def get_config_path() -> Path:
    """Get the path to the config file."""
    # Use ~/.o3de/pilot/config.yaml
    return Path.home() / ".o3de" / "pilot" / "config.yaml"


def get_config() -> "Config":
    """Get the global config instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


class Config:
    """Configuration manager for O3DE Pilot."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or get_config_path()
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from file."""
        if self._path.exists():
            with open(self._path) as f:
                self._data = yaml.safe_load(f) or {}
        else:
            self._data = self._defaults()

    def _defaults(self) -> dict[str, Any]:
        """Default configuration values."""
        return {
            "ai.provider": "none",
            "ai.model": "",
            "ai.api_key": "",
            "ai.ollama_url": "http://localhost:11434",
            "registry.url": "https://canonical.o3de.org",
            "manifest.path": str(Path.home() / ".o3de" / "o3de_manifest.json"),
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value using dot notation."""
        parts = key.split(".")
        value = self._data
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        
        return value

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value using dot notation."""
        parts = key.split(".")
        data = self._data
        
        for part in parts[:-1]:
            if part not in data:
                data[part] = {}
            data = data[part]
        
        data[parts[-1]] = value

    def unset(self, key: str) -> None:
        """Remove a configuration value."""
        parts = key.split(".")
        data = self._data
        
        for part in parts[:-1]:
            if part not in data:
                return
            data = data[part]
        
        if parts[-1] in data:
            del data[parts[-1]]

    def all(self) -> dict[str, Any]:
        """Get all configuration as a flat dictionary."""
        result: dict[str, Any] = {}
        self._flatten(self._data, "", result)
        return result

    def _flatten(self, data: dict[str, Any], prefix: str, result: dict[str, Any]) -> None:
        """Flatten nested dict to dot-notation keys."""
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                self._flatten(value, full_key, result)
            else:
                result[full_key] = value

    def save(self) -> None:
        """Save configuration to file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            yaml.dump(self._data, f, default_flow_style=False)
