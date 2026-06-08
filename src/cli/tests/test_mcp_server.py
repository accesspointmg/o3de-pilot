# O3DE Pilot - MCP Server Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for the MCP server module."""

import json
import pytest
from unittest.mock import patch, MagicMock
from io import StringIO

from o3de_pilot.mcp_server import (
    _tool_to_cli_args,
    _invoke_cli,
    _handle_initialize,
    _handle_tools_list,
    _handle_tools_call,
    _TOOLS,
)


# ── Tool definitions ─────────────────────────────────────────────────

class TestToolDefinitions:
    """Verify tool definitions are well-formed."""

    def test_all_tools_have_name(self):
        for tool in _TOOLS:
            assert "name" in tool
            assert isinstance(tool["name"], str)

    def test_all_tools_have_description(self):
        for tool in _TOOLS:
            assert "description" in tool
            assert len(tool["description"]) > 0

    def test_all_tools_have_input_schema(self):
        for tool in _TOOLS:
            assert "inputSchema" in tool
            assert tool["inputSchema"]["type"] == "object"

    def test_expected_tools_present(self):
        names = {t["name"] for t in _TOOLS}
        assert "workspace_list" in names
        assert "workspace_show" in names
        assert "workspace_create" in names
        assert "workspace_delete" in names
        assert "workspace_build" in names
        assert "workspace_solve" in names
        assert "registry_search" in names
        assert "gem_list" in names
        assert "engine_list" in names
        assert "project_list" in names
        assert "audit" in names
        assert "config_get" in names
        assert "config_set" in names
        assert "gem_info" in names
        assert "registry_install" in names
        assert "deps_tree" in names
        assert "deps_why" in names


# ── Tool → CLI mapping ───────────────────────────────────────────────

class TestToolToCliArgs:
    """Verify tool calls map to correct CLI arguments."""

    def test_workspace_list(self):
        args = _tool_to_cli_args("workspace_list", {})
        assert args[-3:] == ["workspace", "list", "--json"]

    def test_workspace_show(self):
        args = _tool_to_cli_args("workspace_show", {"name_or_path": "my-ws"})
        assert "workspace" in args
        assert "show" in args
        assert "my-ws" in args
        assert "--json" in args

    def test_workspace_create_minimal(self):
        args = _tool_to_cli_args("workspace_create", {"name": "test"})
        assert "workspace" in args
        assert "create" in args
        assert "test" in args
        assert "--json" in args

    def test_workspace_create_full(self):
        args = _tool_to_cli_args("workspace_create", {
            "name": "test",
            "engine": "/path/engine",
            "project": "/path/project",
            "no_solve": True,
            "auto_install": True,
        })
        assert "--engine" in args
        assert "/path/engine" in args
        assert "--project" in args
        assert "--no-solve" in args
        assert "-y" in args

    def test_workspace_delete(self):
        args = _tool_to_cli_args("workspace_delete", {"name_or_path": "old-ws"})
        assert "delete" in args
        assert "old-ws" in args
        assert "--force" in args  # Always force via MCP
        assert "--json" in args

    def test_workspace_build(self):
        args = _tool_to_cli_args("workspace_build", {
            "name_or_path": "ws",
            "config": "debug",
            "dry_run": True,
        })
        assert "build" in args
        assert "--config" in args
        assert "debug" in args
        assert "--dry-run" in args
        assert "--json" in args

    def test_workspace_build_generator(self):
        args = _tool_to_cli_args("workspace_build", {
            "name_or_path": "ws",
            "generator": "ninja",
        })
        assert "--generator" in args
        assert "ninja" in args

    def test_workspace_solve(self):
        args = _tool_to_cli_args("workspace_solve", {
            "name_or_path": "ws",
            "include_store": True,
        })
        assert "solve" in args
        assert "--include-store" in args

    def test_registry_search(self):
        args = _tool_to_cli_args("registry_search", {
            "query": "physics",
            "type": "gem",
        })
        assert "search" in args
        assert "physics" in args
        assert "--type" in args
        assert "gem" in args

    def test_manifest_show(self):
        args = _tool_to_cli_args("manifest_show", {})
        assert "manifest" in args
        assert "show" in args

    def test_gem_list(self):
        args = _tool_to_cli_args("gem_list", {})
        assert "gem" in args
        assert "list" in args

    def test_engine_list(self):
        args = _tool_to_cli_args("engine_list", {})
        assert "engine" in args
        assert "list" in args

    def test_project_list(self):
        args = _tool_to_cli_args("project_list", {})
        assert "project" in args
        assert "list" in args

    def test_audit(self):
        args = _tool_to_cli_args("audit", {"path": "/my/project"})
        assert "audit" in args
        assert "/my/project" in args

    def test_config_get_all(self):
        args = _tool_to_cli_args("config_get", {})
        assert args[-2:] == ["get", "--json"]

    def test_config_get_key(self):
        args = _tool_to_cli_args("config_get", {"key": "ai.provider"})
        assert "ai.provider" in args
        assert "--json" in args

    def test_config_set(self):
        args = _tool_to_cli_args("config_set", {"key": "ai.provider", "value": "ollama"})
        assert "set" in args
        assert "ai.provider" in args
        assert "ollama" in args
        assert "--json" in args

    def test_gem_info(self):
        args = _tool_to_cli_args("gem_info", {"name": "PhysX"})
        assert "gem" in args
        assert "info" in args
        assert "PhysX" in args
        assert "--json" in args

    def test_registry_install_minimal(self):
        args = _tool_to_cli_args("registry_install", {"package": "Atom"})
        assert "registry" in args
        assert "install" in args
        assert "Atom" in args
        assert "--json" in args

    def test_registry_install_full(self):
        args = _tool_to_cli_args("registry_install", {
            "package": "Atom",
            "version": "1.2.3",
            "dry_run": True,
        })
        assert "--version" in args
        assert "1.2.3" in args
        assert "--dry-run" in args

    def test_deps_tree_no_args(self):
        args = _tool_to_cli_args("deps_tree", {})
        assert "deps" in args
        assert "tree" in args
        assert "--json" in args

    def test_deps_tree_with_name(self):
        args = _tool_to_cli_args("deps_tree", {"name": "PhysX"})
        assert "PhysX" in args
        assert "--json" in args

    def test_deps_tree_with_depth(self):
        args = _tool_to_cli_args("deps_tree", {"depth": 3})
        assert "--depth" in args
        assert "3" in args

    def test_deps_why(self):
        args = _tool_to_cli_args("deps_why", {"name": "MyGem", "dependency": "PhysX"})
        assert "deps" in args
        assert "why" in args
        assert "MyGem" in args
        assert "PhysX" in args
        assert "--json" in args

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            _tool_to_cli_args("nonexistent_tool", {})


# ── CLI invocation ────────────────────────────────────────────────────

class TestInvokeCli:
    """Test CLI subprocess invocation wrapper."""

    def test_valid_json_output(self):
        result_json = json.dumps({"status": "ok", "data": {"key": "val"}})
        mock_result = MagicMock()
        mock_result.stdout = result_json
        mock_result.returncode = 0

        with patch("o3de_pilot.mcp_server.subprocess.run", return_value=mock_result):
            result = _invoke_cli(["test"])

        assert result["status"] == "ok"
        assert result["data"]["key"] == "val"

    def test_invalid_json_returns_error(self):
        mock_result = MagicMock()
        mock_result.stdout = "Not JSON output"
        mock_result.returncode = 0

        with patch("o3de_pilot.mcp_server.subprocess.run", return_value=mock_result):
            result = _invoke_cli(["test"])

        assert result["status"] == "error"
        assert result["code"] == "E_INVALID_JSON"

    def test_empty_stdout_with_error(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Something went wrong"
        mock_result.returncode = 1

        with patch("o3de_pilot.mcp_server.subprocess.run", return_value=mock_result):
            result = _invoke_cli(["test"])

        assert result["status"] == "error"
        assert result["code"] == "E_CLI_FAILED"

    def test_empty_stdout_success(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0

        with patch("o3de_pilot.mcp_server.subprocess.run", return_value=mock_result):
            result = _invoke_cli(["test"])

        assert result["status"] == "ok"


# ── MCP protocol handlers ────────────────────────────────────────────

class TestMCPHandlers:
    """Test MCP protocol handler functions."""

    def test_initialize_returns_protocol_version(self):
        result = _handle_initialize({})
        assert result["protocolVersion"] == "2024-11-05"
        assert result["serverInfo"]["name"] == "o3de-pilot"
        assert "tools" in result["capabilities"]

    def test_tools_list_returns_all_tools(self):
        result = _handle_tools_list({})
        assert "tools" in result
        assert len(result["tools"]) == len(_TOOLS)

    def test_tools_call_invokes_cli(self):
        cli_result = json.dumps({"status": "ok", "data": {"workspaces": []}})
        mock_result = MagicMock()
        mock_result.stdout = cli_result
        mock_result.returncode = 0

        with patch("o3de_pilot.mcp_server.subprocess.run", return_value=mock_result):
            result = _handle_tools_call({"name": "workspace_list", "arguments": {}})

        assert "content" in result
        assert len(result["content"]) == 1
        assert result["content"][0]["type"] == "text"
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["status"] == "ok"

    def test_tools_call_error_returns_is_error(self):
        with patch("o3de_pilot.mcp_server._tool_to_cli_args", side_effect=ValueError("bad")):
            result = _handle_tools_call({"name": "bad_tool", "arguments": {}})

        assert result.get("isError") is True
        parsed = json.loads(result["content"][0]["text"])
        assert parsed["status"] == "error"
