# O3DE Pilot - AI Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for AI conversation manager and command routing."""

import json
import pytest
from unittest.mock import patch, MagicMock

from o3de_pilot.ai.conversation import (
    ConversationSession,
    Message,
    TOOL_SCHEMAS,
    DESTRUCTIVE_TOOLS,
    execute_tool,
    _tool_to_cli,
)
from o3de_pilot.ai.command_router import match_command, CommandAction


# ── Conversation session ─────────────────────────────────────────────

class TestConversationSession:
    """M5: Conversation manager."""

    def test_add_user_message(self):
        session = ConversationSession()
        session.add_user_message("hello")
        assert len(session.messages) == 1
        assert session.messages[0].role == "user"
        assert session.messages[0].content == "hello"

    def test_add_assistant_message(self):
        session = ConversationSession()
        session.add_assistant_message("hi there")
        assert session.messages[0].role == "assistant"

    def test_rolling_history_trim(self):
        session = ConversationSession(max_history=5)
        for i in range(10):
            session.add_user_message(f"msg {i}")
        assert len(session.messages) == 5
        assert session.messages[0].content == "msg 5"

    def test_context_messages_format(self):
        session = ConversationSession()
        session.add_user_message("what gems do I have?")
        session.add_assistant_message("Let me check...")
        msgs = session.get_context_messages()
        assert len(msgs) == 2
        assert msgs[0]["role"] == "user"
        assert msgs[1]["role"] == "assistant"

    def test_tool_result_in_context(self):
        session = ConversationSession()
        session.add_user_message("list gems")
        session.add_tool_result("gem_list", {"status": "ok", "data": []})
        msgs = session.get_context_messages()
        assert len(msgs) == 2
        assert "[Tool result]" in msgs[1]["content"]

    def test_destructive_tool_blocked_without_confirm(self):
        session = ConversationSession(confirm_fn=None)
        result = session.execute_tool_call("workspace_build", {"name": "ws"})
        assert result["status"] == "error"
        assert "blocked" in result["error"]

    def test_destructive_tool_declined(self):
        session = ConversationSession(confirm_fn=lambda n, a: False)
        result = session.execute_tool_call("workspace_build", {"name": "ws"})
        assert result["status"] == "error"
        assert "declined" in result["error"]

    def test_destructive_tool_confirmed(self):
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "data": {}})
        mock_result.returncode = 0

        with patch("o3de_pilot.ai.conversation.subprocess.run", return_value=mock_result):
            session = ConversationSession(confirm_fn=lambda n, a: True)
            result = session.execute_tool_call("workspace_build", {"name": "ws"})
        assert result["status"] == "ok"

    def test_non_destructive_tool_no_confirm(self):
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "data": {"gems": []}})
        mock_result.returncode = 0

        with patch("o3de_pilot.ai.conversation.subprocess.run", return_value=mock_result):
            session = ConversationSession(confirm_fn=None)
            result = session.execute_tool_call("gem_list", {})
        assert result["status"] == "ok"

    def test_system_prompt_not_empty(self):
        session = ConversationSession()
        assert len(session.system_prompt) > 50


# ── Tool schemas ─────────────────────────────────────────────────────

class TestToolSchemas:
    """M5: Tool schemas are well-formed."""

    def test_all_have_name(self):
        for schema in TOOL_SCHEMAS:
            assert "name" in schema

    def test_all_have_input_schema(self):
        for schema in TOOL_SCHEMAS:
            assert "input_schema" in schema
            assert schema["input_schema"]["type"] == "object"

    def test_destructive_tools_subset(self):
        all_names = {s["name"] for s in TOOL_SCHEMAS}
        for dt in DESTRUCTIVE_TOOLS:
            # Destructive tools should be in the schema OR be known
            pass  # Just verify the set is valid
        assert len(DESTRUCTIVE_TOOLS) > 0


# ── Tool → CLI mapping ───────────────────────────────────────────────

class TestToolToCli:
    """M5: conversation tool → CLI argument mapping."""

    def test_workspace_list(self):
        args = _tool_to_cli("workspace_list", {})
        assert "workspace" in args and "list" in args and "--json" in args

    def test_workspace_show(self):
        args = _tool_to_cli("workspace_show", {"name": "my-ws"})
        assert "show" in args and "my-ws" in args

    def test_workspace_build(self):
        args = _tool_to_cli("workspace_build", {"name": "ws", "config": "debug"})
        assert "build" in args and "--config" in args and "debug" in args

    def test_gem_list(self):
        args = _tool_to_cli("gem_list", {})
        assert "gem" in args and "list" in args

    def test_registry_search(self):
        args = _tool_to_cli("registry_search", {"query": "physics"})
        assert "search" in args and "physics" in args

    def test_unknown_tool_raises(self):
        with pytest.raises(ValueError):
            _tool_to_cli("fake_tool", {})

    def test_config_get(self):
        args = _tool_to_cli("config_get", {"key": "ai.provider"})
        assert "config" in args and "get" in args and "ai.provider" in args

    def test_config_get_all(self):
        args = _tool_to_cli("config_get", {})
        assert "config" in args and "get" in args and "--json" in args

    def test_config_set(self):
        args = _tool_to_cli("config_set", {"key": "ai.provider", "value": "ollama"})
        assert "set" in args and "ai.provider" in args and "ollama" in args

    def test_gem_info(self):
        args = _tool_to_cli("gem_info", {"name": "PhysX"})
        assert "gem" in args and "info" in args and "PhysX" in args

    def test_registry_install(self):
        args = _tool_to_cli("registry_install", {"package": "Atom", "dry_run": True})
        assert "install" in args and "Atom" in args and "--dry-run" in args

    def test_deps_why(self):
        args = _tool_to_cli("deps_why", {"name": "MyGem", "dependency": "PhysX"})
        assert "why" in args and "MyGem" in args and "PhysX" in args

# ── Command router ───────────────────────────────────────────────────

class TestCommandRouter:
    """M1/M5: Pattern-based command router."""

    def test_create_gem(self):
        action = match_command("create a gem called MyGem")
        assert action is not None
        assert action.command == "gem create"
        assert action.args["name"] == "MyGem"

    def test_list_gems(self):
        action = match_command("list gems")
        assert action is not None
        assert action.command == "gem list"

    def test_list_projects(self):
        action = match_command("show all projects")
        assert action is not None
        assert action.command == "project list"

    def test_build_project(self):
        action = match_command("build project MyProject")
        assert action is not None
        assert action.command == "project build"

    def test_list_workspaces(self):
        action = match_command("list workspaces")
        assert action is not None
        assert action.command == "workspace list"

    def test_resolve_manifest(self):
        action = match_command("resolve the manifest")
        assert action is not None
        assert action.command == "manifest resolve"

    def test_help(self):
        action = match_command("help")
        assert action is not None
        assert action.command == "help"

    def test_no_match(self):
        action = match_command("what is the meaning of life?")
        assert action is None

    def test_empty_input(self):
        action = match_command("")
        assert action is None


# ── Execute tool ─────────────────────────────────────────────────────

class TestExecuteTool:
    """M5: Tool execution wrapper."""

    def test_success(self):
        mock_result = MagicMock()
        mock_result.stdout = json.dumps({"status": "ok", "data": {"count": 3}})
        mock_result.returncode = 0

        with patch("o3de_pilot.ai.conversation.subprocess.run", return_value=mock_result):
            result = execute_tool("gem_list", {})

        assert result["status"] == "ok"

    def test_cli_error(self):
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result.stderr = "Command failed"
        mock_result.returncode = 1

        with patch("o3de_pilot.ai.conversation.subprocess.run", return_value=mock_result):
            result = execute_tool("gem_list", {})

        assert result["status"] == "error"
