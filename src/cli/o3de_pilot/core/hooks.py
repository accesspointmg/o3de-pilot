# O3DE Pilot - Hooks Execution Engine
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Hooks execution engine for O3DE objects.

Objects can define hooks in their JSON metadata:
    "hooks": {
        "post_install": "scripts/setup.py",
        "pre_build": "scripts/prebuild.sh"
    }

The engine runs these scripts with user confirmation (sandboxing/security).
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("o3de_pilot.hooks")


class HookError(Exception):
    """Error during hook execution."""
    pass


class HooksEngine:
    """Execute hooks defined in O3DE object metadata.

    Security: All hooks require explicit user confirmation before execution.
    Hooks run in the object's directory with a timeout.
    """

    def __init__(
        self,
        confirm: bool = True,
        timeout: int = 300,
        dry_run: bool = False,
    ):
        """
        Args:
            confirm: Require user confirmation before running hooks
            timeout: Maximum seconds per hook execution
            dry_run: Show what would run without executing
        """
        self.confirm = confirm
        self.timeout = timeout
        self.dry_run = dry_run

    def run_hook(
        self,
        hook_type: str,
        script_path: str,
        object_dir: Path,
        object_name: str,
        confirm_callback: Optional[callable] = None,
    ) -> bool:
        """Run a single hook script.

        Args:
            hook_type: "post_install" or "pre_build"
            script_path: Relative path to script from object_dir
            object_dir: Root directory of the O3DE object
            object_name: Name of the object (for logging)
            confirm_callback: Optional callback for confirmation; if None,
                uses default console prompt. Should return True to proceed.

        Returns:
            True if hook ran successfully (or was skipped in dry-run)
        """
        full_path = object_dir / script_path

        if not full_path.exists():
            logger.warning(f"Hook script not found: {full_path}")
            return False

        logger.info(f"Hook [{hook_type}] for {object_name}: {full_path}")

        if self.dry_run:
            logger.info(f"Dry-run: would execute {full_path}")
            return True

        if self.confirm:
            if confirm_callback:
                approved = confirm_callback(hook_type, script_path, object_name)
            else:
                approved = self._default_confirm(hook_type, script_path, object_name)
            if not approved:
                logger.info(f"Hook [{hook_type}] skipped by user for {object_name}")
                return False

        return self._execute(full_path, object_dir, hook_type, object_name)

    def run_hooks_for_object(
        self,
        data: dict,
        object_dir: Path,
        object_name: str,
        hook_filter: Optional[list[str]] = None,
        confirm_callback: Optional[callable] = None,
    ) -> dict[str, bool]:
        """Run all hooks defined in an object's data.

        Args:
            data: Object JSON data (raw dict)
            object_dir: Root directory of the O3DE object
            object_name: Name of the object
            hook_filter: Only run these hook types (e.g., ["post_install"])
            confirm_callback: Optional confirmation callback

        Returns:
            Dict of hook_type -> success status
        """
        results: dict[str, bool] = {}

        # Find hooks in data — check inside type dict and root level
        hooks = None
        for type_key in ["engine", "project", "gem", "template", "overlay"]:
            type_data = data.get(type_key, {})
            if isinstance(type_data, dict) and "hooks" in type_data:
                hooks = type_data["hooks"]
                break

        if not hooks:
            hooks = data.get("hooks", {})

        if not hooks or not isinstance(hooks, dict):
            return results

        for hook_type, script_path in hooks.items():
            if hook_filter and hook_type not in hook_filter:
                continue
            if not script_path:
                continue
            results[hook_type] = self.run_hook(
                hook_type, script_path, object_dir, object_name,
                confirm_callback=confirm_callback,
            )

        return results

    def _execute(
        self,
        script_path: Path,
        working_dir: Path,
        hook_type: str,
        object_name: str,
    ) -> bool:
        """Execute a hook script safely."""
        # Determine how to run the script
        suffix = script_path.suffix.lower()
        if suffix == ".py":
            cmd = [sys.executable, str(script_path)]
        elif suffix in (".sh", ".bash"):
            cmd = ["bash", str(script_path)]
        elif suffix in (".bat", ".cmd"):
            cmd = ["cmd", "/c", str(script_path)]
        elif suffix == ".ps1":
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        else:
            # Try to run directly (executable permission)
            cmd = [str(script_path)]

        logger.info(f"Executing hook [{hook_type}] for {object_name}: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=str(working_dir),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            if result.stdout:
                logger.info(f"Hook [{hook_type}] stdout:\n{result.stdout}")
            if result.stderr:
                logger.warning(f"Hook [{hook_type}] stderr:\n{result.stderr}")

            if result.returncode != 0:
                logger.error(
                    f"Hook [{hook_type}] for {object_name} failed with code {result.returncode}"
                )
                return False

            logger.info(f"Hook [{hook_type}] for {object_name} completed successfully")
            return True

        except subprocess.TimeoutExpired:
            logger.error(
                f"Hook [{hook_type}] for {object_name} timed out after {self.timeout}s"
            )
            return False
        except FileNotFoundError:
            logger.error(f"Hook [{hook_type}] interpreter not found for {script_path}")
            return False
        except Exception as e:
            logger.error(f"Hook [{hook_type}] for {object_name} error: {e}")
            return False

    @staticmethod
    def _default_confirm(hook_type: str, script_path: str, object_name: str) -> bool:
        """Default console confirmation prompt."""
        try:
            response = input(
                f"\nHook [{hook_type}] wants to run '{script_path}' "
                f"for {object_name}. Allow? [y/N] "
            )
            return response.strip().lower() in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False
