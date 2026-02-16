# O3DE Pilot AI - Command Router
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Maps natural-language prompts to concrete o3de-pilot CLI actions.

The router works in two layers:
    1. **Local pattern matching** — cheap, instant, no AI call needed.
       Catches well-known phrases like "create a new gem called Foo".
    2. **AI classification** — if no local match, the prompt is sent to
       the configured AI provider with a constrained system prompt that
       asks it to return a JSON action rather than free-form text.

Each recognised action is returned as a ``CommandAction`` data-class that
the GUI can confirm with the user before executing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Action model ────────────────────────────────────────────────────

@dataclass
class CommandAction:
    """A recognised o3de-pilot action to execute."""
    command: str                          # e.g. "gem create"
    description: str                      # Human-readable summary
    args: dict[str, str] = field(default_factory=dict)
    confirmed: bool = False               # Set True after user OKs
    raw_prompt: str = ""                  # Original user prompt


# ── Pattern-based router ────────────────────────────────────────────

# Each entry: (compiled regex, builder function)
_PATTERNS: list[tuple[re.Pattern, callable]] = []


def _pattern(pattern: str):
    """Decorator: register a regex → builder."""
    compiled = re.compile(pattern, re.IGNORECASE)
    def decorator(fn):
        _PATTERNS.append((compiled, fn))
        return fn
    return decorator


# -- Gem commands --

@_pattern(r"(?:pilot[,.]?\s+)?create\s+(?:a\s+)?(?:new\s+)?gem(?:\s+(?:called|named))?\s+(?P<name>\S+)")
def _gem_create(m: re.Match) -> CommandAction:
    name = m.group("name").strip("\"'")
    return CommandAction(
        command="gem create",
        description=f"Create a new gem named '{name}'",
        args={"name": name},
    )


@_pattern(r"(?:pilot[,.]?\s+)?create\s+(?:a\s+)?(?:new\s+)?gem\b")
def _gem_create_default(m: re.Match) -> CommandAction:
    return CommandAction(
        command="gem create",
        description="Create a new gem (will prompt for name)",
        args={},
    )


@_pattern(r"(?:pilot[,.]?\s+)?(?:list|show)\s+(?:all\s+)?gems?\b")
def _gem_list(m: re.Match) -> CommandAction:
    return CommandAction(command="gem list", description="List all registered gems")


@_pattern(r"(?:pilot[,.]?\s+)?gem\s+info\s+(?P<name>\S+)")
def _gem_info(m: re.Match) -> CommandAction:
    name = m.group("name").strip("\"'")
    return CommandAction(
        command="gem info",
        description=f"Show info for gem '{name}'",
        args={"name": name},
    )


@_pattern(r"(?:pilot[,.]?\s+)?search\s+(?:for\s+)?gems?\s+(?P<query>.+)")
def _gem_search(m: re.Match) -> CommandAction:
    query = m.group("query").strip("\"'")
    return CommandAction(
        command="gem search",
        description=f"Search gems matching '{query}'",
        args={"query": query},
    )


# -- Project commands --

@_pattern(r"(?:pilot[,.]?\s+)?create\s+(?:a\s+)?(?:new\s+)?project(?:\s+(?:called|named))?\s+(?P<name>\S+)")
def _project_create(m: re.Match) -> CommandAction:
    name = m.group("name").strip("\"'")
    return CommandAction(
        command="project init",
        description=f"Create a new project named '{name}'",
        args={"name": name},
    )


@_pattern(r"(?:pilot[,.]?\s+)?create\s+(?:a\s+)?(?:new\s+)?project\b")
def _project_create_default(m: re.Match) -> CommandAction:
    return CommandAction(
        command="project init",
        description="Create a new project (will prompt for name)",
        args={},
    )


@_pattern(r"(?:pilot[,.]?\s+)?(?:list|show)\s+(?:all\s+)?projects?\b")
def _project_list(m: re.Match) -> CommandAction:
    return CommandAction(command="project list", description="List all registered projects")


@_pattern(r"(?:pilot[,.]?\s+)?build\s+(?:the\s+)?project(?:\s+(?P<name>\S+))?")
def _project_build(m: re.Match) -> CommandAction:
    name = m.group("name") or ""
    desc = f"Build project '{name}'" if name else "Build the current project"
    return CommandAction(command="project build", description=desc, args={"name": name} if name else {})


@_pattern(r"(?:pilot[,.]?\s+)?run\s+(?:the\s+)?project(?:\s+(?P<name>\S+))?")
def _project_run(m: re.Match) -> CommandAction:
    name = m.group("name") or ""
    desc = f"Run project '{name}'" if name else "Run the current project"
    return CommandAction(command="project run", description=desc, args={"name": name} if name else {})


@_pattern(r"(?:pilot[,.]?\s+)?add\s+(?:gem\s+)?(?P<gem>\S+)\s+to\s+(?:project\s+)?(?P<project>\S+)")
def _project_add_gem(m: re.Match) -> CommandAction:
    gem = m.group("gem").strip("\"'")
    project = m.group("project").strip("\"'")
    return CommandAction(
        command="project add",
        description=f"Add gem '{gem}' to project '{project}'",
        args={"gem": gem, "project": project},
    )


# -- Engine commands --

@_pattern(r"(?:pilot[,.]?\s+)?(?:list|show)\s+(?:all\s+)?engines?\b")
def _engine_list(m: re.Match) -> CommandAction:
    return CommandAction(command="engine list", description="List all registered engines")


@_pattern(r"(?:pilot[,.]?\s+)?register\s+engine\s+(?:at\s+)?(?P<path>.+)")
def _engine_register(m: re.Match) -> CommandAction:
    path = m.group("path").strip("\"'")
    return CommandAction(
        command="engine register",
        description=f"Register engine at '{path}'",
        args={"path": path},
    )


# -- Layout commands --

@_pattern(r"(?:pilot[,.]?\s+)?create\s+(?:a\s+)?layout\s+(?:for\s+)?(?P<project>\S+)")
def _layout_create(m: re.Match) -> CommandAction:
    project = m.group("project").strip("\"'")
    return CommandAction(
        command="layout create",
        description=f"Create layout for project '{project}'",
        args={"project": project},
    )


@_pattern(r"(?:pilot[,.]?\s+)?(?:list|show)\s+layouts?\b")
def _layout_list(m: re.Match) -> CommandAction:
    return CommandAction(command="layout list", description="List all layouts")


# -- Manifest / Registry --

@_pattern(r"(?:pilot[,.]?\s+)?resolve\s+(?:the\s+)?manifest\b")
def _manifest_resolve(m: re.Match) -> CommandAction:
    return CommandAction(command="manifest resolve", description="Resolve the manifest")


@_pattern(r"(?:pilot[,.]?\s+)?refresh\s+(?:the\s+)?(?:registry|store|remotes?)\b")
def _registry_refresh(m: re.Match) -> CommandAction:
    return CommandAction(command="registry refresh", description="Refresh remote registries")


@_pattern(r"(?:pilot[,.]?\s+)?(?:install|download)\s+(?P<name>\S+)")
def _registry_install(m: re.Match) -> CommandAction:
    name = m.group("name").strip("\"'")
    return CommandAction(
        command="registry install",
        description=f"Install '{name}' from the registry",
        args={"name": name},
    )


# -- Deps --

@_pattern(r"(?:pilot[,.]?\s+)?(?:show|display)\s+(?:the\s+)?dep(?:endency)?\s+tree\b")
def _deps_tree(m: re.Match) -> CommandAction:
    return CommandAction(command="deps tree", description="Show the dependency tree")


@_pattern(r"(?:pilot[,.]?\s+)?audit\s+(?:the\s+)?(?:project|dependencies|deps)\b")
def _audit(m: re.Match) -> CommandAction:
    return CommandAction(command="audit", description="Audit dependencies for issues")


# -- Help / general --

@_pattern(r"(?:pilot[,.]?\s+)?(?:help|what can you do|commands)\b")
def _help(m: re.Match) -> CommandAction:
    return CommandAction(command="help", description="Show available commands")


# ── Public API ──────────────────────────────────────────────────────

def match_command(prompt: str) -> Optional[CommandAction]:
    """
    Try to match *prompt* against known command patterns.

    Returns a ``CommandAction`` if a local match is found, or ``None``
    if the prompt should be forwarded to the AI provider.
    """
    text = prompt.strip()
    if not text:
        return None

    for pattern, builder in _PATTERNS:
        m = pattern.search(text)
        if m:
            action = builder(m)
            action.raw_prompt = text
            return action

    return None


def get_ai_classification_prompt(user_prompt: str) -> str:
    """
    Build a system+user prompt for the AI to classify an unknown command.

    The AI should return JSON like:
        {"command": "gem create", "args": {"name": "Foo"}, "description": "..."}
    or:
        {"command": "chat", "response": "Here is a free-form answer..."}
    """
    commands_list = [
        "gem create <name>", "gem list", "gem info <name>", "gem search <query>",
        "project init <name>", "project list", "project build [name]",
        "project run [name]", "project add <gem> --project <project>",
        "engine list", "engine register <path>", "engine unregister <path>",
        "template info <name>",
        "layout create <project>", "layout list", "layout show <name>",
        "manifest resolve", "manifest show", "manifest upgrade",
        "registry refresh", "registry install <name>", "registry uninstall <name>",
        "registry search <query>",
        "deps tree", "audit",
        "config get <key>", "config set <key> <value>",
        "publish <path>",
        "help",
    ]
    commands_str = "\n".join(f"  - {c}" for c in commands_list)

    return f"""You are the O3DE Pilot AI assistant. The user said:

\"{user_prompt}\"

Your job is to determine if this maps to one of these o3de-pilot commands:
{commands_str}

If it clearly maps to a command, respond with ONLY this JSON (no markdown, no extra text):
{{"command": "<command>", "args": {{"<key>": "<value>"}}, "description": "<one-line summary>"}}

If it does NOT map to any command and is a general question, respond with:
{{"command": "chat", "response": "<your helpful answer>"}}

Respond with ONLY the JSON object, nothing else."""


AVAILABLE_COMMANDS = [
    ("gem create <name>", "Create a new gem"),
    ("gem list", "List all registered gems"),
    ("gem info <name>", "Show gem details"),
    ("gem search <query>", "Search for gems"),
    ("project init <name>", "Create a new project"),
    ("project list", "List all projects"),
    ("project build [name]", "Build a project"),
    ("project run [name]", "Run a project"),
    ("project add <gem>", "Add a gem to a project"),
    ("engine list", "List registered engines"),
    ("layout create <project>", "Create a layout"),
    ("layout list", "List layouts"),
    ("manifest resolve", "Resolve the manifest"),
    ("registry refresh", "Refresh remote registries"),
    ("registry install <name>", "Install from registry"),
    ("deps tree", "Show dependency tree"),
    ("audit", "Audit dependencies"),
    ("help", "Show available commands"),
]
