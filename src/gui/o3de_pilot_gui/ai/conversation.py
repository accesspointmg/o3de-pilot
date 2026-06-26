# O3DE Pilot AI - Conversation Manager
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Conversation manager for multi-turn AI interactions with tool calling.

Provides a session-based conversation loop where the AI can:
- Maintain rolling message history
- Call o3de-pilot CLI commands as tools
- Auto-inject workspace context
- Require confirmation for destructive actions
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Message model
# ---------------------------------------------------------------------------

@dataclass
class Message:
    """A single message in a conversation."""
    role: str  # "user", "assistant", "system", "tool_result"
    content: str
    tool_call: dict[str, Any] | None = None
    tool_result: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Tool definitions for AI
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "workspace_list",
        "description": "List all workspaces",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "workspace_show",
        "description": "Show details of a workspace",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "workspace_build",
        "description": "Build a workspace. Destructive: requires confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "config": {"type": "string", "enum": ["debug", "profile", "release"]},
                "dry_run": {"type": "boolean"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "gem_list",
        "description": "List all registered gems",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "engine_list",
        "description": "List all registered engines",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "project_list",
        "description": "List all registered projects",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "registry_search",
        "description": "Search the registry",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "manifest_show",
        "description": "Show the resolved manifest",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "deps_tree",
        "description": "Show the dependency tree",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "audit",
        "description": "Audit schema compliance",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
    {
        "name": "config_get",
        "description": "Get configuration value(s)",
        "input_schema": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
        },
    },
    {
        "name": "config_set",
        "description": "Set a configuration value. Destructive: requires confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "gem_info",
        "description": "Get detailed information about a gem",
        "input_schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
    },
    {
        "name": "registry_install",
        "description": "Install a package from the registry. Destructive: requires confirmation.",
        "input_schema": {
            "type": "object",
            "properties": {
                "package": {"type": "string"},
                "version": {"type": "string"},
                "dry_run": {"type": "boolean"},
            },
            "required": ["package"],
        },
    },
    {
        "name": "deps_why",
        "description": "Explain why an object depends on another",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "dependency": {"type": "string"},
            },
            "required": ["name", "dependency"],
        },
    },
]

# Actions that require user confirmation before execution
DESTRUCTIVE_TOOLS = {"workspace_build", "workspace_delete", "workspace_create", "config_set", "registry_install"}


# ---------------------------------------------------------------------------
# Tool execution
# ---------------------------------------------------------------------------

def _tool_to_cli(name: str, args: dict[str, Any]) -> list[str]:
    """Map tool name + args to CLI arguments with --json."""
    base = [sys.executable, "-m", "o3de_cli"]
    parts = name.split("_", 1)

    if name == "workspace_list":
        return base + ["workspace", "list", "--json"]
    if name == "workspace_show":
        return base + ["workspace", "show", args["name"], "--json"]
    if name == "workspace_build":
        cmd = base + ["workspace", "build", args["name"], "--json"]
        if args.get("config"):
            cmd += ["--config", args["config"]]
        if args.get("dry_run"):
            cmd += ["--dry-run"]
        return cmd
    if name == "gem_list":
        return base + ["gem", "list", "--json"]
    if name == "engine_list":
        return base + ["engine", "list", "--json"]
    if name == "project_list":
        return base + ["project", "list", "--json"]
    if name == "registry_search":
        return base + ["registry", "search", args["query"], "--json"]
    if name == "manifest_show":
        return base + ["manifest", "show", "--json"]
    if name == "deps_tree":
        return base + ["deps", "tree", "--json"]
    if name == "audit":
        return base + ["audit", args["path"], "--json"]
    if name == "config_get":
        cmd = base + ["config", "get", "--json"]
        if args.get("key"):
            cmd.append(args["key"])
        return cmd
    if name == "config_set":
        return base + ["config", "set", "--json", args["key"], args["value"]]
    if name == "gem_info":
        return base + ["gem", "info", args["name"], "--json"]
    if name == "registry_install":
        cmd = base + ["registry", "install", args["package"], "--json"]
        if args.get("version"):
            cmd += ["--version", args["version"]]
        if args.get("dry_run"):
            cmd += ["--dry-run"]
        return cmd
    if name == "deps_why":
        return base + ["deps", "why", args["name"], args["dependency"], "--json"]

    raise ValueError(f"Unknown tool: {name}")


def execute_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Execute a tool and return the JSON result."""
    cli_args = _tool_to_cli(name, args)
    result = subprocess.run(
        cli_args, capture_output=True, text=True, timeout=300,
    )
    stdout = result.stdout.strip()
    if stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"status": "error", "error": stdout}
    if result.returncode != 0:
        return {"status": "error", "error": result.stderr.strip() or f"Exit code {result.returncode}"}
    return {"status": "ok", "data": {}}


# ---------------------------------------------------------------------------
# Conversation session
# ---------------------------------------------------------------------------

class ConversationSession:
    """Manages a multi-turn conversation with rolling history.

    Parameters
    ----------
    max_history : int
        Maximum messages to keep in history (older messages are dropped).
    confirm_fn : callable | None
        Callback ``confirm_fn(tool_name, args) -> bool`` for destructive
        action gates.  If *None*, destructive tools are always blocked.
    """

    def __init__(
        self,
        *,
        max_history: int = 40,
        confirm_fn: Callable[[str, dict], bool] | None = None,
    ) -> None:
        self.messages: list[Message] = []
        self.max_history = max_history
        self.confirm_fn = confirm_fn

    @property
    def system_prompt(self) -> str:
        return (
            "You are an expert assistant for o3de-pilot, the CLI/GUI manager "
            "for the Open 3D Engine (O3DE).\n\n"
            "You have access to tools that call o3de-pilot CLI commands. "
            "Use them when the user asks about their workspaces, gems, engines, "
            "projects, or build status. Always prefer calling a tool over "
            "guessing.\n\n"
            "When a user asks to do something destructive (build, delete, "
            "create), explain what will happen and confirm before proceeding.\n\n"
            "Keep responses concise and practical."
        )

    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))
        self._trim()

    def add_assistant_message(self, content: str) -> None:
        self.messages.append(Message(role="assistant", content=content))
        self._trim()

    def add_tool_result(self, tool_name: str, result: dict) -> None:
        self.messages.append(Message(
            role="tool_result",
            content=json.dumps(result, indent=2),
            tool_result={"tool": tool_name, "result": result},
        ))
        self._trim()

    def get_context_messages(self) -> list[dict[str, str]]:
        """Return messages formatted for the AI provider."""
        out: list[dict[str, str]] = []
        for msg in self.messages:
            if msg.role in ("user", "assistant"):
                out.append({"role": msg.role, "content": msg.content})
            elif msg.role == "tool_result":
                out.append({"role": "user", "content": f"[Tool result]\n{msg.content}"})
        return out

    def execute_tool_call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool call with optional confirmation gate."""
        if name in DESTRUCTIVE_TOOLS:
            if self.confirm_fn is None:
                return {"status": "error", "error": f"Destructive action '{name}' blocked (no confirmation handler)"}
            if not self.confirm_fn(name, args):
                return {"status": "error", "error": f"User declined '{name}'"}

        result = execute_tool(name, args)
        self.add_tool_result(name, result)
        return result

    def _trim(self) -> None:
        """Keep history within max_history limit."""
        if len(self.messages) > self.max_history:
            self.messages = self.messages[-self.max_history:]
