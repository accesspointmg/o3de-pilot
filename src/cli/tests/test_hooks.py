# O3DE Pilot - Hooks Engine Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for o3de_pilot.core.hooks module."""

import pytest
import tempfile
import sys
from pathlib import Path

from o3de_pilot.core.hooks import HooksEngine, HookError


class TestHooksEngineInit:
    """Test HooksEngine initialization."""

    def test_default_init(self):
        engine = HooksEngine()
        assert engine.confirm is True
        assert engine.timeout == 300
        assert engine.dry_run is False

    def test_custom_init(self):
        engine = HooksEngine(confirm=False, timeout=60, dry_run=True)
        assert engine.confirm is False
        assert engine.timeout == 60
        assert engine.dry_run is True


class TestRunHook:
    """Test running individual hooks."""

    def test_dry_run_does_not_execute(self, tmp_path):
        """Dry-run should not execute the script."""
        script = tmp_path / "hook.py"
        script.write_text('raise Exception("Should not run")')

        engine = HooksEngine(dry_run=True, confirm=False)
        result = engine.run_hook("post_install", "hook.py", tmp_path, "test-gem")
        assert result is True

    def test_missing_script_returns_false(self, tmp_path):
        engine = HooksEngine(confirm=False)
        result = engine.run_hook("post_install", "missing.py", tmp_path, "test-gem")
        assert result is False

    def test_execute_python_script(self, tmp_path):
        """Should execute a python hook script successfully."""
        script = tmp_path / "hook.py"
        script.write_text('print("hook ran")')

        engine = HooksEngine(confirm=False)
        result = engine.run_hook("post_install", "hook.py", tmp_path, "test-gem")
        assert result is True

    def test_execute_failing_script(self, tmp_path):
        """Should return False for a script that exits non-zero."""
        script = tmp_path / "hook.py"
        script.write_text("import sys; sys.exit(1)")

        engine = HooksEngine(confirm=False)
        result = engine.run_hook("post_install", "hook.py", tmp_path, "test-gem")
        assert result is False

    def test_confirm_callback_allows(self, tmp_path):
        script = tmp_path / "hook.py"
        script.write_text('print("ok")')

        engine = HooksEngine(confirm=True)
        result = engine.run_hook(
            "post_install", "hook.py", tmp_path, "test-gem",
            confirm_callback=lambda *args: True,
        )
        assert result is True

    def test_confirm_callback_denies(self, tmp_path):
        script = tmp_path / "hook.py"
        script.write_text('print("ok")')

        engine = HooksEngine(confirm=True)
        result = engine.run_hook(
            "post_install", "hook.py", tmp_path, "test-gem",
            confirm_callback=lambda *args: False,
        )
        assert result is False


class TestRunHooksForObject:
    """Test running all hooks for an O3DE object."""

    def test_no_hooks(self, tmp_path):
        engine = HooksEngine(confirm=False)
        results = engine.run_hooks_for_object({}, tmp_path, "test-gem")
        assert results == {}

    def test_hooks_in_root(self, tmp_path):
        script = tmp_path / "setup.py"
        script.write_text('print("setup")')

        data = {"hooks": {"post_install": "setup.py"}}
        engine = HooksEngine(confirm=False)
        results = engine.run_hooks_for_object(data, tmp_path, "test-gem")
        assert results.get("post_install") is True

    def test_hooks_in_type_dict(self, tmp_path):
        script = tmp_path / "setup.py"
        script.write_text('print("setup")')

        data = {"gem": {"hooks": {"post_install": "setup.py"}}}
        engine = HooksEngine(confirm=False)
        results = engine.run_hooks_for_object(data, tmp_path, "test-gem")
        assert results.get("post_install") is True

    def test_hook_filter(self, tmp_path):
        script1 = tmp_path / "install.py"
        script1.write_text('print("install")')
        script2 = tmp_path / "build.py"
        script2.write_text('print("build")')

        data = {"hooks": {"post_install": "install.py", "pre_build": "build.py"}}
        engine = HooksEngine(confirm=False)
        results = engine.run_hooks_for_object(
            data, tmp_path, "test-gem",
            hook_filter=["post_install"],
        )
        assert "post_install" in results
        assert "pre_build" not in results

    def test_dry_run_all_hooks(self, tmp_path):
        data = {"hooks": {"post_install": "setup.py", "pre_build": "build.py"}}
        # Scripts don't need to exist for dry run since it checks existence
        # but run_hook returns False if the file doesn't exist, so create them
        (tmp_path / "setup.py").write_text("")
        (tmp_path / "build.py").write_text("")

        engine = HooksEngine(dry_run=True, confirm=False)
        results = engine.run_hooks_for_object(data, tmp_path, "test-gem")
        assert results.get("post_install") is True
        assert results.get("pre_build") is True


class TestHookError:
    """Test HookError exception."""

    def test_is_exception(self):
        error = HookError("hook failed")
        assert isinstance(error, Exception)
        assert str(error) == "hook failed"
