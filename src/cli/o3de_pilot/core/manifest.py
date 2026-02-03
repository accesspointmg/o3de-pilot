# O3DE Pilot CLI - Manifest
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""O3DE manifest management."""

from pathlib import Path
from typing import Any
from pydantic import BaseModel
import json


class ProjectInfo(BaseModel):
    """Information about a registered project."""
    name: str
    path: Path
    engine_name: str | None = None
    version: str | None = None


class GemInfo(BaseModel):
    """Information about a registered gem."""
    name: str
    path: Path
    version: str | None = None


class TemplateInfo(BaseModel):
    """Information about a registered template."""
    name: str
    path: Path
    template_type: str | None = None


class EngineInfo(BaseModel):
    """Information about a registered engine."""
    name: str
    path: Path
    version: str | None = None


class Manifest:
    """O3DE manifest manager."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or (Path.home() / ".o3de" / "o3de_manifest.json")
        self._data: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load manifest from file."""
        if self._path.exists():
            with open(self._path) as f:
                self._data = json.load(f)
        else:
            self._data = {
                "projects": [],
                "external_subdirectories": [],
                "templates": [],
                "restricted": [],
                "repos": [],
                "engines": [],
                "default_engines_folder": "",
                "default_projects_folder": "",
                "default_gems_folder": "",
                "default_templates_folder": "",
                "default_restricted_folder": "",
            }

    def get_projects(self) -> list[ProjectInfo]:
        """Get all registered projects."""
        projects = []
        for path_str in self._data.get("projects", []):
            path = Path(path_str)
            if path.exists():
                project_json = path / "project.json"
                if project_json.exists():
                    with open(project_json) as f:
                        data = json.load(f)
                        projects.append(ProjectInfo(
                            name=data.get("project_name", path.name),
                            path=path,
                            engine_name=data.get("engine"),
                            version=data.get("version"),
                        ))
        return projects

    def get_gems(self) -> list[GemInfo]:
        """Get all registered gems."""
        gems = []
        for path_str in self._data.get("external_subdirectories", []):
            path = Path(path_str)
            gem_json = path / "gem.json"
            if gem_json.exists():
                with open(gem_json) as f:
                    data = json.load(f)
                    gems.append(GemInfo(
                        name=data.get("gem_name", path.name),
                        path=path,
                        version=data.get("version"),
                    ))
        return gems

    def get_templates(self) -> list[TemplateInfo]:
        """Get all registered templates."""
        templates = []
        for path_str in self._data.get("templates", []):
            path = Path(path_str)
            template_json = path / "template.json"
            if template_json.exists():
                with open(template_json) as f:
                    data = json.load(f)
                    templates.append(TemplateInfo(
                        name=data.get("template_name", path.name),
                        path=path,
                        template_type=data.get("template_type"),
                    ))
        return templates

    def get_engines(self) -> list[EngineInfo]:
        """Get all registered engines."""
        engines = []
        for path_str in self._data.get("engines", []):
            path = Path(path_str)
            engine_json = path / "engine.json"
            if engine_json.exists():
                with open(engine_json) as f:
                    data = json.load(f)
                    engines.append(EngineInfo(
                        name=data.get("engine_name", path.name),
                        path=path,
                        version=data.get("version"),
                    ))
        return engines

    def save(self) -> None:
        """Save manifest to file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._data, f, indent=4)


_manifest_instance: Manifest | None = None


def get_manifest() -> Manifest:
    """Get the global manifest instance."""
    global _manifest_instance
    if _manifest_instance is None:
        _manifest_instance = Manifest()
    return _manifest_instance
