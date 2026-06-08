# O3DE Pilot - MCP Server
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""MCP (Model Context Protocol) server exposing o3de-pilot CLI as tools.

Each tool maps to a CLI command invoked with ``--json``.  The server
runs over stdio and is compatible with VS Code Copilot, Claude, and any
MCP-compliant client.

Start with::

    o3de-pilot mcp          # via CLI
    python -m o3de_pilot.mcp_server   # directly
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

_TOOLS: list[dict[str, Any]] = [
    {
        "name": "workspace_list",
        "description": "List all workspaces.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "workspace_show",
        "description": "Show details of a specific workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_or_path": {
                    "type": "string",
                    "description": "Workspace name or path.",
                },
            },
            "required": ["name_or_path"],
        },
    },
    {
        "name": "workspace_create",
        "description": "Create a new workspace from an engine and/or project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Workspace name."},
                "engine": {"type": "string", "description": "Engine path."},
                "project": {"type": "string", "description": "Project path."},
                "output": {"type": "string", "description": "Output directory."},
                "no_solve": {"type": "boolean", "description": "Skip dependency resolution."},
                "auto_install": {"type": "boolean", "description": "Auto-install remote deps."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "workspace_delete",
        "description": "Delete a workspace (symlinks only, not source files).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_or_path": {"type": "string", "description": "Workspace name or path."},
            },
            "required": ["name_or_path"],
        },
    },
    {
        "name": "workspace_build",
        "description": "Configure and build a workspace with CMake.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_or_path": {"type": "string", "description": "Workspace name or path."},
                "config": {"type": "string", "description": "Build config (debug/profile/release).", "default": "profile"},
                "generator": {"type": "string", "description": "CMake generator (auto/vs/ninja/xcode)."},
                "configure_only": {"type": "boolean", "description": "Only run configure step."},
                "build_only": {"type": "boolean", "description": "Only run build step (skip configure)."},
                "dry_run": {"type": "boolean", "description": "Show commands without executing."},
            },
            "required": ["name_or_path"],
        },
    },
    {
        "name": "workspace_solve",
        "description": "Solve dependencies for a workspace.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name_or_path": {"type": "string", "description": "Workspace name or path."},
                "include_store": {"type": "boolean", "description": "Include remote store."},
            },
            "required": ["name_or_path"],
        },
    },
    {
        "name": "registry_search",
        "description": "Search the registry for objects (engines, gems, projects, templates).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query."},
                "type": {"type": "string", "description": "Object type filter.", "enum": ["engine", "gem", "project", "template"]},
            },
            "required": ["query"],
        },
    },
    {
        "name": "manifest_show",
        "description": "Show the resolved manifest.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "gem_list",
        "description": "List all registered gems.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "engine_list",
        "description": "List all registered engines.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "project_list",
        "description": "List all registered projects.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "audit",
        "description": "Audit schema compliance for o3de objects.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to audit."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "config_get",
        "description": "Get a configuration value or all config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Config key (omit for all)."},
            },
        },
    },
    {
        "name": "config_set",
        "description": "Set a configuration value.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Config key."},
                "value": {"type": "string", "description": "Value to set."},
            },
            "required": ["key", "value"],
        },
    },
    {
        "name": "gem_info",
        "description": "Get detailed information about a gem.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Gem name."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "registry_install",
        "description": "Install a package from the registry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "package": {"type": "string", "description": "Package name."},
                "version": {"type": "string", "description": "Specific version."},
                "dry_run": {"type": "boolean", "description": "Preview without installing."},
            },
            "required": ["package"],
        },
    },
    {
        "name": "deps_tree",
        "description": "Visualize the dependency graph as a JSON tree.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Root object name (omit for full forest)."},
                "depth": {"type": "integer", "description": "Max tree depth."},
            },
        },
    },
    {
        "name": "deps_why",
        "description": "Explain why an object depends on another (dependency chain).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Source object."},
                "dependency": {"type": "string", "description": "Target dependency."},
            },
            "required": ["name", "dependency"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool → CLI mapping
# ---------------------------------------------------------------------------

def _tool_to_cli_args(name: str, arguments: dict[str, Any]) -> list[str]:
    """Convert an MCP tool call into CLI arguments (always includes --json)."""
    base = [sys.executable, "-m", "o3de_pilot"]

    if name == "workspace_list":
        return base + ["workspace", "list", "--json"]

    if name == "workspace_show":
        return base + ["workspace", "show", arguments["name_or_path"], "--json"]

    if name == "workspace_create":
        cmd = base + ["workspace", "create", arguments["name"], "--json"]
        if arguments.get("engine"):
            cmd += ["--engine", arguments["engine"]]
        if arguments.get("project"):
            cmd += ["--project", arguments["project"]]
        if arguments.get("output"):
            cmd += ["--output", arguments["output"]]
        if arguments.get("no_solve"):
            cmd += ["--no-solve"]
        if arguments.get("auto_install"):
            cmd += ["-y"]
        return cmd

    if name == "workspace_delete":
        return base + ["workspace", "delete", arguments["name_or_path"], "--force", "--json"]

    if name == "workspace_build":
        cmd = base + ["workspace", "build", arguments["name_or_path"], "--json"]
        if arguments.get("config"):
            cmd += ["--config", arguments["config"]]
        if arguments.get("generator"):
            cmd += ["--generator", arguments["generator"]]
        if arguments.get("configure_only"):
            cmd += ["--configure-only"]
        if arguments.get("build_only"):
            cmd += ["--build-only"]
        if arguments.get("dry_run"):
            cmd += ["--dry-run"]
        return cmd

    if name == "workspace_solve":
        cmd = base + ["workspace", "solve", arguments["name_or_path"], "--json"]
        if arguments.get("include_store"):
            cmd += ["--include-store"]
        return cmd

    if name == "registry_search":
        cmd = base + ["registry", "search", arguments["query"], "--json"]
        if arguments.get("type"):
            cmd += ["--type", arguments["type"]]
        return cmd

    if name == "manifest_show":
        return base + ["manifest", "show", "--json"]

    if name == "gem_list":
        return base + ["gem", "list", "--json"]

    if name == "engine_list":
        return base + ["engine", "list", "--json"]

    if name == "project_list":
        return base + ["project", "list", "--json"]

    if name == "audit":
        return base + ["audit", arguments["path"], "--json"]

    if name == "config_get":
        cmd = base + ["config", "get", "--json"]
        if arguments.get("key"):
            cmd.append(arguments["key"])
        return cmd

    if name == "config_set":
        return base + ["config", "set", "--json", arguments["key"], arguments["value"]]

    if name == "gem_info":
        return base + ["gem", "info", arguments["name"], "--json"]

    if name == "registry_install":
        cmd = base + ["registry", "install", arguments["package"], "--json"]
        if arguments.get("version"):
            cmd += ["--version", arguments["version"]]
        if arguments.get("dry_run"):
            cmd += ["--dry-run"]
        return cmd

    if name == "deps_tree":
        cmd = base + ["deps", "tree", "--json"]
        if arguments.get("name"):
            cmd.insert(-1, arguments["name"])
        if arguments.get("depth"):
            cmd += ["--depth", str(arguments["depth"])]
        return cmd

    if name == "deps_why":
        return base + ["deps", "why", arguments["name"], arguments["dependency"], "--json"]

    raise ValueError(f"Unknown tool: {name}")


def _invoke_cli(args: list[str]) -> dict[str, Any]:
    """Run CLI command and return parsed JSON result."""
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=300,
    )
    stdout = result.stdout.strip()
    if stdout:
        try:
            return json.loads(stdout)
        except json.JSONDecodeError:
            return {"status": "error", "error": stdout, "code": "E_INVALID_JSON"}
    if result.returncode != 0:
        return {
            "status": "error",
            "error": result.stderr.strip() or f"Exit code {result.returncode}",
            "code": "E_CLI_FAILED",
        }
    return {"status": "ok", "data": {}}


# ---------------------------------------------------------------------------
# JSON-RPC stdio transport
# ---------------------------------------------------------------------------

def _read_message() -> dict[str, Any] | None:
    """Read a JSON-RPC message from stdin (Content-Length framing)."""
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            return None  # EOF
        line = line.strip()
        if not line:
            break  # end of headers
        if ":" in line:
            key, _, value = line.partition(":")
            headers[key.strip().lower()] = value.strip()

    length = int(headers.get("content-length", 0))
    if length == 0:
        return None
    body = sys.stdin.read(length)
    return json.loads(body)


def _write_message(msg: dict[str, Any]) -> None:
    """Write a JSON-RPC message to stdout (Content-Length framing)."""
    body = json.dumps(msg)
    header = f"Content-Length: {len(body)}\r\n\r\n"
    sys.stdout.write(header)
    sys.stdout.write(body)
    sys.stdout.flush()


def _jsonrpc_response(id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _jsonrpc_error(id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


# ---------------------------------------------------------------------------
# MCP protocol handlers
# ---------------------------------------------------------------------------

_SERVER_INFO = {
    "name": "o3de-pilot",
    "version": "0.1.0",
}

_CAPABILITIES = {
    "tools": {},
}


def _handle_initialize(params: dict) -> dict:
    return {
        "protocolVersion": "2024-11-05",
        "serverInfo": _SERVER_INFO,
        "capabilities": _CAPABILITIES,
    }


def _handle_tools_list(params: dict) -> dict:
    return {"tools": _TOOLS}


def _handle_tools_call(params: dict) -> dict:
    name = params["name"]
    arguments = params.get("arguments", {})
    try:
        cli_args = _tool_to_cli_args(name, arguments)
        result = _invoke_cli(cli_args)
        return {
            "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
        }
    except Exception as exc:
        return {
            "content": [{"type": "text", "text": json.dumps({
                "status": "error",
                "error": str(exc),
                "code": "E_MCP_INTERNAL",
            })}],
            "isError": True,
        }


_HANDLERS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}

# Notifications (no response needed)
_NOTIFICATIONS = {"notifications/initialized", "initialized"}


def serve() -> None:
    """Run the MCP server on stdio."""
    while True:
        msg = _read_message()
        if msg is None:
            break

        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        # Notifications have no id — don't respond
        if msg_id is None or method in _NOTIFICATIONS:
            continue

        handler = _HANDLERS.get(method)
        if handler is None:
            _write_message(_jsonrpc_error(msg_id, -32601, f"Unknown method: {method}"))
            continue

        try:
            result = handler(params)
            _write_message(_jsonrpc_response(msg_id, result))
        except Exception as exc:
            _write_message(_jsonrpc_error(msg_id, -32603, str(exc)))


if __name__ == "__main__":
    serve()
