# O3DE Pilot - Command Router Tests
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for ai.command_router pattern matching."""

import pytest
from o3de_pilot.ai.command_router import match_command, CommandAction


class TestGemPatterns:
    def test_create_gem_named(self):
        a = match_command("create a new gem called MyPhysics")
        assert a is not None
        assert a.command == "gem create"
        assert a.args["name"] == "MyPhysics"

    def test_create_gem_no_name(self):
        a = match_command("create a gem")
        assert a is not None
        assert a.command == "gem create"

    def test_list_gems(self):
        a = match_command("list gems")
        assert a is not None
        assert a.command == "gem list"

    def test_show_all_gems(self):
        a = match_command("show all gems")
        assert a is not None
        assert a.command == "gem list"

    def test_gem_info(self):
        a = match_command("gem info org.o3de.gem.physx")
        assert a is not None
        assert a.command == "gem info"
        assert a.args["name"] == "org.o3de.gem.physx"

    def test_search_gems(self):
        a = match_command("search for gems physics")
        assert a is not None
        assert a.command == "gem search"

    def test_pilot_prefix(self):
        a = match_command("pilot, create gem called Foo")
        assert a is not None
        assert a.command == "gem create"


class TestProjectPatterns:
    def test_create_project_named(self):
        a = match_command("create a new project called MyGame")
        assert a is not None
        assert a.command == "project init"
        assert a.args["name"] == "MyGame"

    def test_create_project_default(self):
        a = match_command("create a project")
        assert a is not None
        assert a.command == "project init"

    def test_list_projects(self):
        a = match_command("list projects")
        assert a is not None
        assert a.command == "project list"

    def test_build_project(self):
        a = match_command("build the project")
        assert a is not None
        assert a.command == "project build"

    def test_build_specific_project(self):
        a = match_command("build project MyGame")
        assert a is not None
        assert a.command == "project build"
        assert a.args.get("name") == "MyGame"

    def test_run_project(self):
        a = match_command("run the project")
        assert a is not None
        assert a.command == "project run"

    def test_add_gem_to_project(self):
        a = match_command("add org.o3de.gem.physx to MyProject")
        assert a is not None
        assert a.command == "project add"
        assert a.args["gem"] == "org.o3de.gem.physx"
        assert a.args["project"] == "MyProject"


class TestEnginePatterns:
    def test_list_engines(self):
        a = match_command("list engines")
        assert a is not None
        assert a.command == "engine list"

    def test_register_engine(self):
        a = match_command("register engine at /path/to/engine")
        assert a is not None
        assert a.command == "engine register local"
        assert a.args["path_or_url"] == "/path/to/engine"


class TestWorkspacePatterns:
    def test_create_workspace(self):
        a = match_command("create a workspace for MyProject")
        assert a is not None
        assert a.command == "workspace create"
        assert a.args["project"] == "MyProject"

    def test_list_workspaces(self):
        a = match_command("list workspaces")
        assert a is not None
        assert a.command == "workspace list"


class TestManifestPatterns:
    def test_resolve(self):
        a = match_command("resolve the manifest")
        assert a is not None
        assert a.command == "manifest resolve"

    def test_refresh_registry(self):
        a = match_command("refresh the registry")
        assert a is not None
        assert a.command == "registry refresh"

    def test_install(self):
        a = match_command("install org.o3de.gem.atomrenderer")
        assert a is not None
        assert a.command == "registry install"


class TestDepsPatterns:
    def test_dep_tree(self):
        a = match_command("show the dependency tree")
        assert a is not None
        assert a.command == "deps tree"

    def test_audit(self):
        a = match_command("audit the dependencies")
        assert a is not None
        assert a.command == "audit"


class TestGeneralPatterns:
    def test_help(self):
        a = match_command("help")
        assert a is not None
        assert a.command == "help"

    def test_no_match(self):
        a = match_command("what is the meaning of life?")
        assert a is None

    def test_empty_input(self):
        a = match_command("")
        assert a is None

    def test_whitespace_only(self):
        a = match_command("   ")
        assert a is None

    def test_raw_prompt_preserved(self):
        a = match_command("list gems")
        assert a.raw_prompt == "list gems"


class TestCommandAction:
    def test_defaults(self):
        a = CommandAction(command="test", description="desc")
        assert a.confirmed is False
        assert a.raw_prompt == ""
        assert a.args == {}
