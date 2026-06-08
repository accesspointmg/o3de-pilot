# O3DE Pilot - Shared Test Fixtures
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Centralized pytest fixtures for o3de-pilot tests.

Provides:
- runner: CliRunner instance
- temp_manifest: minimal valid manifest file
- temp_gem / temp_project / temp_engine / temp_template: object dirs
- mock_manifest: patches get_manifest_path at ALL import sites
- mock_store: MagicMock(spec=Store) with preset stubs
- resolved_manifest_factory: writes resolved manifest with configurable objects
- make_gem helper: creates gem dir with full JSON
"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from click.testing import CliRunner


# ---------------------------------------------------------------------------
# Basic runner
# ---------------------------------------------------------------------------

@pytest.fixture
def runner():
    """Click test runner with stderr separated."""
    return CliRunner()


# ---------------------------------------------------------------------------
# Minimal JSON templates
# ---------------------------------------------------------------------------

_MANIFEST_TEMPLATE = {
    "$schema": "https://canonical.o3de.org/o3de-manifest-2.0.0.json",
    "$schemaVersion": "2.0.0",
    "o3de_manifest": {
        "name": "test",
    },
    "local": {
        "engines": [],
        "projects": [],
        "gems": [],
        "templates": [],
        "repos": [],
        "overlays": [],
    },
    "remote_repos": [],
}

_GEM_TEMPLATE = {
    "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
    "$schemaVersion": "2.0.0",
    "gem": {
        "name": "org.test.gem.{name}",
        "version": "1.0.0",
        "display_name": "{display}",
    },
}

_PROJECT_TEMPLATE = {
    "$schema": "https://canonical.o3de.org/o3de-project-2.0.0.json",
    "$schemaVersion": "2.0.0",
    "project": {
        "name": "org.test.project.{name}",
        "version": "1.0.0",
        "display_name": "{display}",
    },
}

_ENGINE_TEMPLATE = {
    "$schema": "https://canonical.o3de.org/o3de-engine-2.0.0.json",
    "$schemaVersion": "2.0.0",
    "engine": {
        "name": "org.test.engine.{name}",
        "version": "1.0.0",
        "display_name": "{display}",
    },
}

_TEMPLATE_TEMPLATE = {
    "$schema": "https://canonical.o3de.org/o3de-template-2.0.0.json",
    "$schemaVersion": "2.0.0",
    "template": {
        "name": "org.test.template.{name}",
        "version": "1.0.0",
        "display_name": "{display}",
    },
}


# ---------------------------------------------------------------------------
# Object directory fixtures
# ---------------------------------------------------------------------------

def _write_json(path: Path, data: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))
    return path


@pytest.fixture
def temp_manifest(tmp_path):
    """Create a minimal valid manifest and return its path."""
    manifest_path = tmp_path / "o3de_manifest.2-0-0.json"
    _write_json(manifest_path, _MANIFEST_TEMPLATE)
    return manifest_path


@pytest.fixture
def temp_gem(tmp_path):
    """Create a minimal gem directory and return its path."""
    gem_dir = tmp_path / "TestGem"
    gem_dir.mkdir()
    data = json.loads(json.dumps(_GEM_TEMPLATE))
    data["gem"]["name"] = "org.test.gem.testgem"
    data["gem"]["display_name"] = "Test Gem"
    _write_json(gem_dir / "gem.2-0-0.json", data)
    return gem_dir


@pytest.fixture
def temp_project(tmp_path):
    """Create a minimal project directory and return its path."""
    proj_dir = tmp_path / "TestProject"
    proj_dir.mkdir()
    data = json.loads(json.dumps(_PROJECT_TEMPLATE))
    data["project"]["name"] = "org.test.project.testproject"
    data["project"]["display_name"] = "Test Project"
    _write_json(proj_dir / "project.2-0-0.json", data)
    return proj_dir


@pytest.fixture
def temp_engine(tmp_path):
    """Create a minimal engine directory and return its path."""
    eng_dir = tmp_path / "TestEngine"
    eng_dir.mkdir()
    data = json.loads(json.dumps(_ENGINE_TEMPLATE))
    data["engine"]["name"] = "org.test.engine.testengine"
    data["engine"]["display_name"] = "Test Engine"
    _write_json(eng_dir / "engine.2-0-0.json", data)
    return eng_dir


@pytest.fixture
def temp_template(tmp_path):
    """Create a minimal template directory and return its path."""
    tpl_dir = tmp_path / "TestTemplate"
    tpl_dir.mkdir()
    data = json.loads(json.dumps(_TEMPLATE_TEMPLATE))
    data["template"]["name"] = "org.test.template.testtemplate"
    data["template"]["display_name"] = "Test Template"
    _write_json(tpl_dir / "template.2-0-0.json", data)
    return tpl_dir


# ---------------------------------------------------------------------------
# make_gem helper
# ---------------------------------------------------------------------------

def make_gem(
    base_path: Path,
    name: str,
    version: str = "1.0.0",
    deps: list[str] | None = None,
    optional_deps: list[str] | None = None,
    display_name: str | None = None,
) -> Path:
    """
    Create a gem directory with a full 2.0.0 JSON file.

    Args:
        base_path: Parent directory to create the gem in.
        name: Canonical gem name (e.g. "org.o3de.gem.physx").
        version: Semantic version string.
        deps: List of dependency specifiers.
        optional_deps: List of optional dependency specifiers.
        display_name: Human-readable name (defaults to last segment of name).

    Returns:
        Path to the gem directory.
    """
    short = name.rsplit(".", 1)[-1]
    gem_dir = base_path / short
    gem_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "$schema": "https://canonical.o3de.org/o3de-gem-2.0.0.json",
        "$schemaVersion": "2.0.0",
        "gem": {
            "name": name,
            "version": version,
            "display_name": display_name or short.replace("_", " ").title(),
        },
    }
    if deps:
        data["gem"]["dependent"] = {"gems": deps}
    if optional_deps:
        data["gem"]["optional_dependent"] = {"gems": optional_deps}
    _write_json(gem_dir / "gem.2-0-0.json", data)
    return gem_dir


# ---------------------------------------------------------------------------
# mock_manifest — patches get_manifest_path everywhere
# ---------------------------------------------------------------------------

# All module-level import sites for get_manifest_path
_MANIFEST_PATH_SITES = [
    "o3de_pilot.core.paths.get_manifest_path",
    "o3de_pilot.core.get_manifest_path",
    "o3de_pilot.commands.manifest.get_manifest_path",
    "o3de_pilot.commands.publish.get_manifest_path",
    "o3de_pilot.commands.register.get_manifest_path",
    "o3de_pilot.commands.deps.get_manifest_path",
    "o3de_pilot.commands.audit.get_manifest_path",
    "o3de_pilot.commands.registry.get_manifest_path",
    "o3de_pilot.core.resolver.get_manifest_path",
]

# All module-level import sites for get_resolved_manifest_path
_RESOLVED_PATH_SITES = [
    "o3de_pilot.core.paths.get_resolved_manifest_path",
    "o3de_pilot.core.get_resolved_manifest_path",
    "o3de_pilot.core.resolver.get_resolved_manifest_path",
    "o3de_pilot.commands.manifest.get_resolved_manifest_path",
    "o3de_pilot.commands.publish.get_resolved_manifest_path",
    "o3de_pilot.commands.registry.get_resolved_manifest_path",
    "o3de_pilot.commands.workspace.get_resolved_manifest_path",
]


@pytest.fixture
def mock_manifest(tmp_path, monkeypatch):
    """
    Patch get_manifest_path and get_resolved_manifest_path at every import
    site so all CLI commands use a temp manifest.

    Returns the manifest file path. The file is pre-populated with
    _MANIFEST_TEMPLATE content; tests can overwrite it as needed.
    """
    manifest_path = tmp_path / "o3de_manifest.2-0-0.json"
    _write_json(manifest_path, _MANIFEST_TEMPLATE)

    resolved_path = tmp_path / "resolved_o3de_manifest.json"

    for site in _MANIFEST_PATH_SITES:
        try:
            monkeypatch.setattr(site, lambda _mp=manifest_path: _mp)
        except AttributeError:
            pass  # module not imported yet — lazy import will hit paths.py

    for site in _RESOLVED_PATH_SITES:
        try:
            monkeypatch.setattr(site, lambda _rp=resolved_path: _rp)
        except AttributeError:
            pass

    return manifest_path


# ---------------------------------------------------------------------------
# mock_store — MagicMock with sensible defaults
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_store():
    """
    Return a MagicMock(spec=Store) with preset stubs.

    - search() returns []
    - download_sync() returns tmp dir path
    - refresh_sync() is a no-op
    """
    from o3de_pilot.core.store import Store

    store = MagicMock(spec=Store)
    store.search.return_value = []
    store.download_sync.return_value = Path("/tmp/mock_download")
    store.refresh_sync.return_value = None
    store.objects = {}
    store.versions = {}
    return store


# ---------------------------------------------------------------------------
# resolved_manifest_factory
# ---------------------------------------------------------------------------

@pytest.fixture
def resolved_manifest_factory(tmp_path):
    """
    Factory fixture: call with a dict of objects to write a resolved manifest.

    Usage:
        resolved = resolved_manifest_factory(gems=[...], projects=[...])
    """
    def _factory(
        gems: list[dict] | None = None,
        projects: list[dict] | None = None,
        engines: list[dict] | None = None,
        templates: list[dict] | None = None,
        overlays: list[dict] | None = None,
    ) -> Path:
        resolved = {
            "resolved_manifest": {
                "gems": gems or [],
                "projects": projects or [],
                "engines": engines or [],
                "templates": templates or [],
                "overlays": overlays or [],
            },
            "file_hashes": {},
        }
        path = tmp_path / "resolved_o3de_manifest.json"
        _write_json(path, resolved)
        return path

    return _factory
