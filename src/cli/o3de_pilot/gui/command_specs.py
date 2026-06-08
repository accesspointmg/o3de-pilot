# O3DE Pilot GUI - Command Specifications
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""
Single source of truth for all CLI commands exposed in the GUI.

Each command spec defines:
    - cli_args: list of CLI tokens (e.g. ["engine", "register"])
    - title: human-readable label
    - description: tooltip / help text
    - fields: list of parameter definitions
    - state_changing: whether the command modifies the manifest / filesystem
    - object_types: which ObjectType values this command applies to (empty = global)
    - context: "global" | "selected" | "both"

Field types:
    "text"   – free text input (QLineEdit)
    "path"   – directory/file picker (QLineEdit + browse button)
    "choice" – dropdown (QComboBox)
    "flag"   – checkbox (QCheckBox)
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Field helper
# ---------------------------------------------------------------------------

def _field(name: str, label: str, ftype: str = "text", *,
           required: bool = False, default: str = "",
           choices: list[str] | None = None,
           placeholder: str = "", from_selected: str = "",
           positional: bool = False, file_filter: str = ""):
    """Build a field dict with sensible defaults.

    Args:
        from_selected: attribute name on ObjectInfo to pre-fill from the
            currently selected object (e.g. "name", "path").
        positional: if True the value is passed as a bare positional
            argument rather than ``--name value``.
        file_filter: file dialog filter string for "file" type fields
            (e.g. "JSON files (*.json)").
    """
    f: dict = {
        "name": name,
        "label": label,
        "type": ftype,
        "required": required,
    }
    if default:
        f["default"] = default
    if choices:
        f["choices"] = choices
    if placeholder:
        f["placeholder"] = placeholder
    if from_selected:
        f["from_selected"] = from_selected
    if positional:
        f["positional"] = True
    if file_filter:
        f["file_filter"] = file_filter
    return f


# ---------------------------------------------------------------------------
# Command specs – organized by toolbar group
# ---------------------------------------------------------------------------

COMMAND_SPECS: dict[str, dict] = {
    # ── Engine ──────────────────────────────────────────────────────
    "engine list": {
        "cli_args": ["engine", "list"],
        "title": "List Engines",
        "description": "List all registered engines.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": ["engine"],
        "context": "global",
        "group": "tools",
    },
    "engine create": {
        "cli_args": ["engine", "create"],
        "title": "New Engine",
        "description": "Create a new engine from a template.",
        "fields": [
            _field("name", "Engine Name", required=True,
                   placeholder="my-engine"),
            _field("path", "Location", "path",
                   placeholder="Parent directory (optional)"),
            _field("template", "Template", placeholder="(default)"),
        ],
        "state_changing": True,
        "object_types": ["engine"],
        "context": "global",
        "group": "new",
    },
    # ── Project ─────────────────────────────────────────────────────
    "project list": {
        "cli_args": ["project", "list"],
        "title": "List Projects",
        "description": "List all registered projects.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": ["project"],
        "context": "global",
        "group": "tools",
    },
    "project init": {
        "cli_args": ["project", "init"],
        "title": "New Project",
        "description": "Create a new project from a template.",
        "fields": [
            _field("name", "Project Name", required=True,
                   placeholder="my-game"),
            _field("path", "Location", "path",
                   placeholder="Parent directory (optional)"),
            _field("template", "Template", placeholder="(default)"),
        ],
        "state_changing": True,
        "object_types": ["project"],
        "context": "global",
        "group": "new",
    },
    "project build": {
        "cli_args": ["project", "build"],
        "title": "Build Project",
        "description": "Build a project with CMake.",
        "fields": [
            _field("path", "Project Path", "path", from_selected="path"),
            _field("config", "Configuration", "choice",
                   default="profile", choices=["debug", "profile", "release"]),
        ],
        "state_changing": True,
        "object_types": ["project"],
        "context": "selected",
        "group": "project",
    },
    "project run": {
        "cli_args": ["project", "run"],
        "title": "Run Project",
        "description": "Launch a project.",
        "fields": [
            _field("path", "Project Path", "path", from_selected="path"),
        ],
        "state_changing": False,
        "object_types": ["project"],
        "context": "selected",
        "group": "project",
    },
    "project add": {
        "cli_args": ["project", "add"],
        "title": "Add Gem to Project",
        "description": "Add a gem dependency to a project.",
        "fields": [
            _field("obj_type", "Type", "choice", default="gem",
                   choices=["gem"]),
            _field("name", "Gem Name", required=True),
            _field("path", "Project Path", "path", from_selected="path"),
        ],
        "state_changing": True,
        "object_types": ["project"],
        "context": "selected",
        "group": "project",
    },

    # ── Gem ──────────────────────────────────────────────────────────
    "gem list": {
        "cli_args": ["gem", "list"],
        "title": "List Gems",
        "description": "List all registered gems.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": ["gem"],
        "context": "global",
        "group": "tools",
    },
    "gem create": {
        "cli_args": ["gem", "create"],
        "title": "New Gem",
        "description": "Create a new gem from a template.",
        "fields": [
            _field("name", "Gem Name", required=True, placeholder="my-gem"),
            _field("path", "Location", "path",
                   placeholder="Parent directory (optional)"),
            _field("template", "Template", placeholder="(default)"),
        ],
        "state_changing": True,
        "object_types": ["gem"],
        "context": "global",
        "group": "new",
    },
    "gem info": {
        "cli_args": ["gem", "info"],
        "title": "Gem Info",
        "description": "Show detailed information about a gem.",
        "fields": [
            _field("name", "Gem Name", required=True, from_selected="name"),
        ],
        "state_changing": False,
        "object_types": ["gem"],
        "context": "selected",
        "group": "tools",
    },
    "gem search": {
        "cli_args": ["gem", "search"],
        "title": "Search Gems",
        "description": "Search for gems by keyword.",
        "fields": [
            _field("query", "Search Query", required=True,
                   placeholder="e.g. physics"),
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": ["gem"],
        "context": "global",
        "group": "registry",
    },

    # ── Template ────────────────────────────────────────────────────
    "template list": {
        "cli_args": ["template", "list"],
        "title": "List Templates",
        "description": "List all available templates.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": ["template"],
        "context": "global",
        "group": "tools",
    },
    "template info": {
        "cli_args": ["template", "info"],
        "title": "Template Info",
        "description": "Show detailed information about a template.",
        "fields": [
            _field("name", "Template Name", required=True,
                   from_selected="name"),
        ],
        "state_changing": False,
        "object_types": ["template"],
        "context": "selected",
        "group": "tools",
    },
    "template create": {
        "cli_args": ["template", "create"],
        "title": "New Template",
        "description": "Create a new template, optionally from a source directory.",
        "fields": [
            _field("name", "Template Name", required=True,
                   placeholder="my-template"),
            _field("path", "Location", "path",
                   placeholder="Parent directory (optional)"),
            _field("source", "Source Directory", "path",
                   placeholder="Existing directory to templatize (optional)"),
        ],
        "state_changing": True,
        "object_types": ["template"],
        "context": "global",
        "group": "new",
    },
    "template instance": {
        "cli_args": ["template", "instance"],
        "title": "Instantiate Template",
        "description": "Create a new object instance from a template.",
        "fields": [
            _field("template_name", "Template", required=True,
                   from_selected="name"),
            _field("name", "Instance Name", required=True,
                   placeholder="my-new-object"),
            _field("path", "Output Path", "path",
                   placeholder="Where to create the instance"),
        ],
        "state_changing": True,
        "object_types": ["template"],
        "context": "selected",
        "group": "new",
    },
    # ── Registry ────────────────────────────────────────────────────
    "registry search": {
        "cli_args": ["registry", "search"],
        "title": "Search Registry",
        "description": "Search for objects in the registry.",
        "fields": [
            _field("query", "Search Query", required=True),
            _field("type", "Object Type", "choice", default="all",
                   choices=["all", "gem", "template", "project", "engine"]),
            _field("remote", "Remote Only", "flag"),
            _field("local", "Local Only", "flag"),
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "registry",
    },
    "registry install": {
        "cli_args": ["registry", "install"],
        "title": "Install Package",
        "description": "Install a package from the registry.",
        "fields": [
            _field("package", "Package Name", required=True,
                   from_selected="name"),
            _field("version", "Version", placeholder="(latest)"),
            _field("path", "Install Path", "path"),
            _field("dry_run", "Dry Run", "flag"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "both",
        "group": "registry",
    },
    "registry uninstall": {
        "cli_args": ["registry", "uninstall"],
        "title": "Uninstall Package",
        "description": "Uninstall a package from the registry.",
        "fields": [
            _field("package", "Package Name", required=True,
                   from_selected="name"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "both",
        "group": "registry",
    },
    "registry update": {
        "cli_args": ["registry", "update"],
        "title": "Update Packages",
        "description": "Update packages from the registry.",
        "fields": [
            _field("package", "Package Name",
                   placeholder="(all if empty)"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "registry",
    },
    "registry refresh": {
        "cli_args": ["registry", "refresh"],
        "title": "Refresh Remote Repos",
        "description": "Re-fetch metadata from all remote repos.",
        "fields": [
            _field("force", "Force Refresh", "flag"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "registry",
    },
    "registry add-remote": {
        "cli_args": ["registry", "add-remote"],
        "title": "Add Remote Repo",
        "description": "Add a remote repo URL to the manifest.",
        "fields": [
            _field("url", "Repo URL", required=True,
                   placeholder="https://..."),
            _field("name", "Display Name"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "registry",
    },
    "registry remove-remote": {
        "cli_args": ["registry", "remove-remote"],
        "title": "Remove Remote Repo",
        "description": "Remove a remote repo URL from the manifest.",
        "fields": [
            _field("url", "Repo URL", required=True),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "registry",
    },
    "registry list-remotes": {
        "cli_args": ["registry", "list-remotes"],
        "title": "List Remote Repos",
        "description": "List all configured remote repos.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "registry",
    },

    # ── Manifest ────────────────────────────────────────────────────
    "manifest resolve": {
        "cli_args": ["manifest", "resolve"],
        "title": "Resolve Manifest",
        "description": "Re-resolve the manifest (rebuild cache).",
        "fields": [
            _field("json", "Output as JSON", "flag"),
            _field("dry_run", "Dry Run", "flag"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "tools",
    },
    "manifest show": {
        "cli_args": ["manifest", "show"],
        "title": "Show Manifest",
        "description": "Display the current manifest contents.",
        "fields": [
            _field("resolved", "Show Resolved", "flag"),
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "tools",
    },
    "manifest upgrade": {
        "cli_args": ["manifest", "upgrade"],
        "title": "Upgrade Manifest Schema",
        "description": "Upgrade object schemas to 2.0.0 format.",
        "fields": [
            _field("path", "Path", "path", placeholder="(current manifest)"),
            _field("recursive", "Recursive", "flag"),
            _field("dry_run", "Dry Run", "flag"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "tools",
    },
    "manifest add": {
        "cli_args": ["manifest", "add"],
        "title": "Add Path to Manifest",
        "description": "Add an object path to the manifest.",
        "fields": [
            _field("path", "Object Path", "path", required=True,
                   from_selected="path"),
            _field("type", "Object Type", "choice",
                   choices=["", "engine", "project", "gem", "template",
                            "repo", "overlay"]),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "both",
        "group": "register",
    },
    "manifest remove": {
        "cli_args": ["manifest", "remove"],
        "title": "Remove Path from Manifest",
        "description": "Remove an object path from the manifest.",
        "fields": [
            _field("path", "Object Path", "path", required=True,
                   from_selected="path"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "selected",
        "group": "register",
    },
    "manifest set": {
        "cli_args": ["manifest", "set"],
        "title": "Set Manifest Value",
        "description": "Set a key-value pair in the manifest.",
        "fields": [
            _field("key", "Key", required=True,
                   placeholder="e.g. country.code"),
            _field("value", "Value", required=True),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "tools",
    },
    "manifest get": {
        "cli_args": ["manifest", "get"],
        "title": "Get Manifest Value",
        "description": "Get a value from the manifest.",
        "fields": [
            _field("key", "Key", placeholder="(all if empty)"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "tools",
    },

    # ── Workspace (symlinked build dirs) ──────────────────────────────
    "workspace create": {
        "cli_args": ["workspace", "create"],
        "title": "Create Workspace",
        "description": "Create a symlinked workspace for a project + engine.",
        "fields": [
            _field("name", "Workspace Name", required=True, positional=True),
            _field("engine", "Engine Path", "path"),
            _field("project", "Project Path", "path"),
            _field("output", "Output Directory", "path"),
            _field("no_overlays", "Skip Overlays", "flag"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "workspace",
    },
    "workspace update": {
        "cli_args": ["workspace", "update"],
        "title": "Update Workspace",
        "description": "Re-sync an existing workspace's symlinks.",
        "fields": [
            _field("name_or_path", "Workspace Name or Path", required=True),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "workspace",
    },
    "workspace list": {
        "cli_args": ["workspace", "list"],
        "title": "List Workspaces",
        "description": "List all known workspaces.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "workspace",
    },
    "workspace show": {
        "cli_args": ["workspace", "show"],
        "title": "Show Workspace",
        "description": "Show details of a workspace.",
        "fields": [
            _field("name_or_path", "Workspace Name or Path", required=True),
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "workspace",
    },
    "workspace delete": {
        "cli_args": ["workspace", "delete"],
        "title": "Delete Workspace",
        "description": "Delete a workspace directory.",
        "fields": [
            _field("name_or_path", "Workspace Name or Path", required=True),
            _field("force", "Force (no confirmation)", "flag"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "workspace",
    },
    "workspace tree": {
        "cli_args": ["workspace", "tree"],
        "title": "Workspace File Tree",
        "description": "Show the file tree of a workspace.",
        "fields": [
            _field("name_or_path", "Workspace Name or Path", required=True),
            _field("depth", "Depth", default="2"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "workspace",
    },
    "workspace solve": {
        "cli_args": ["workspace", "solve"],
        "title": "Solve Workspace Dependencies",
        "description": "Resolve transitive dependencies for a workspace root object.",
        "fields": [
            _field("root_name", "Root Object Name", required=True),
            _field("include_store", "Include Store", "flag"),
            _field("json", "Output as JSON", "flag"),
            _field("dry_run", "Dry Run", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "workspace",
    },

    # ── Repo ─────────────────────────────────────────────────────────
    "repo list": {
        "cli_args": ["repo", "list"],
        "title": "List Repos",
        "description": "List all registered repos.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": ["repo"],
        "context": "global",
        "group": "tools",
    },
    "repo create": {
        "cli_args": ["repo", "create"],
        "title": "New Repo",
        "description": "Create a new repo from a template.",
        "fields": [
            _field("name", "Repo Name", required=True,
                   placeholder="my-repo"),
            _field("path", "Location", "path",
                   placeholder="Parent directory (optional)"),
            _field("template", "Template", placeholder="(default)"),
        ],
        "state_changing": True,
        "object_types": ["repo"],
        "context": "global",
        "group": "new",
    },

    # ── Overlay ──────────────────────────────────────────────────────
    "overlay list": {
        "cli_args": ["overlay", "list"],
        "title": "List Overlays",
        "description": "List all registered overlays.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": ["overlay"],
        "context": "global",
        "group": "tools",
    },
    "overlay create": {
        "cli_args": ["overlay", "create"],
        "title": "New Overlay",
        "description": "Create a new overlay from a template.",
        "fields": [
            _field("name", "Overlay Name", required=True,
                   placeholder="my-overlay"),
            _field("path", "Location", "path",
                   placeholder="Parent directory (optional)"),
            _field("template", "Template", placeholder="(default)"),
        ],
        "state_changing": True,
        "object_types": ["overlay"],
        "context": "global",
        "group": "new",
    },

    # (Old standalone workspace commands removed — workspace now means
    #  the symlinked build directory, defined above.)

    # ── Publish ─────────────────────────────────────────────────────
    "publish validate": {
        "cli_args": ["publish", "validate"],
        "title": "Validate for Publishing",
        "description": "Validate an object is ready for publishing.",
        "fields": [
            _field("path", "Object Path", "path", required=True,
                   from_selected="path"),
            _field("strict", "Strict Mode", "flag"),
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "both",
        "group": "tools",
    },
    "publish push": {
        "cli_args": ["publish", "push"],
        "title": "Publish to Remote",
        "description": "Push object metadata to a remote repo.",
        "fields": [
            _field("path", "Object Path", "path", required=True,
                   from_selected="path"),
            _field("remote", "Remote Name"),
            _field("dry_run", "Dry Run", "flag"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "selected",
        "group": "tools",
    },

    # ── Deps ────────────────────────────────────────────────────────
    "deps tree": {
        "cli_args": ["deps", "tree"],
        "title": "Dependency Tree",
        "description": "Show the dependency tree of an object.",
        "fields": [
            _field("name", "Object Name", from_selected="name"),
            _field("depth", "Depth", default="10"),
            _field("all", "Show All Objects", "flag"),
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "both",
        "group": "tools",
    },
    "deps list": {
        "cli_args": ["deps", "list"],
        "title": "List Dependencies",
        "description": "List direct dependencies of an object.",
        "fields": [
            _field("name", "Object Name", required=True,
                   from_selected="name"),
            _field("transitive", "Include Transitive", "flag"),
            _field("reverse", "Reverse (Dependants)", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "both",
        "group": "tools",
    },
    "deps why": {
        "cli_args": ["deps", "why"],
        "title": "Explain Dependency",
        "description": "Explain why an object depends on another.",
        "fields": [
            _field("name", "Object Name", required=True,
                   from_selected="name"),
            _field("dependency", "Dependency Name", required=True),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "selected",
        "group": "tools",
    },

    # ── Audit ───────────────────────────────────────────────────────
    "audit": {
        "cli_args": ["audit"],
        "title": "Audit Dependencies",
        "description": "Scan for dependency issues, deprecation, and conflicts.",
        "fields": [
            _field("json", "Output as JSON", "flag"),
        ],
        "state_changing": False,
        "object_types": [],
        "context": "global",
        "group": "tools",
    },

    # ── Unified Register / Unregister ───────────────────────────────
    "register local": {
        "cli_args": ["register"],
        "title": "Local",
        "description": "Register a local object by selecting its JSON file (e.g. gem.json, engine.json).",
        "fields": [
            _field("path", "Object JSON File", "file", required=True,
                   placeholder="Select engine.json, gem.json, project.json, etc.",
                   from_selected="path", positional=True,
                   file_filter="O3DE Object Files (engine.json gem.json project.json template.json repo.json overlay.json);;All JSON (*.json);;All Files (*)"),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "both",
        "group": "register",
    },
    "register remote": {
        "cli_args": ["register", "--remote"],
        "title": "Remote",
        "description": "Register a remote object by URL.",
        "fields": [
            _field("url", "Object URL", required=True,
                   placeholder="https://example.com/gem.json", positional=True),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "register",
    },
    "unregister local": {
        "cli_args": ["unregister"],
        "title": "Local",
        "description": "Unregister a local object by its path.",
        "fields": [
            _field("path", "Object Path", "path", required=True,
                   placeholder="Path to object directory",
                   from_selected="path", positional=True),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "selected",
        "group": "unregister",
    },
    "unregister remote": {
        "cli_args": ["unregister", "--remote"],
        "title": "Remote",
        "description": "Unregister a remote object by name or URL.",
        "fields": [
            _field("name", "Object Name / URL", required=True, positional=True),
        ],
        "state_changing": True,
        "object_types": [],
        "context": "global",
        "group": "unregister",
    },
}


# ---------------------------------------------------------------------------
# Toolbar groups — defines the dropdown menus and their order
# ---------------------------------------------------------------------------

TOOLBAR_GROUPS = [
    {
        "id": "new",
        "label": "New",
        "tooltip": "Create new objects",
        "commands": [
            "project init", "gem create",
            "engine create", "template create",
            "repo create", "overlay create",
            "---",
            "template instance",
        ],
    },
    {
        "id": "register",
        "label": "Register",
        "tooltip": "Register objects (local path or remote URL)",
        "commands": [
            "register local", "register remote",
        ],
    },
    {
        "id": "unregister",
        "label": "Unregister",
        "tooltip": "Unregister objects (local or remote)",
        "commands": [
            "unregister local", "unregister remote",
        ],
    },
    {
        "id": "workspace",
        "label": "Workspace",
        "tooltip": "Symlinked build workspaces",
        "commands": [
            "workspace create", "workspace update",
            "---",
            "workspace list", "workspace show", "workspace tree",
            "---",
            "workspace delete",
        ],
    },
    {
        "id": "tools",
        "label": "Tools",
        "tooltip": "Registry, manifest, dependencies, publishing",
        "commands": [
            "registry search", "gem search",
            "---",
            "registry install", "registry uninstall", "registry update",
            "---",
            "registry refresh",
            "registry add-remote", "registry remove-remote",
            "registry list-remotes",
            "---",
            "manifest resolve", "manifest show", "manifest upgrade",
            "manifest set", "manifest get",
            "---",
            "deps tree", "deps list", "deps why",
            "---",
            "audit",
            "---",
            "publish validate", "publish push",
        ],
    },
]


# ---------------------------------------------------------------------------
# Context menu: commands per object type (for right-click)
# ---------------------------------------------------------------------------

CONTEXT_MENU_COMMANDS: dict[str, list[str]] = {
    "engine": [
        "engine create",
        "---",
        "deps tree", "deps list",
        "---",
        "publish validate",
    ],
    "project": [
        "project build", "project run",
        "---",
        "project add",
        "---",
        "deps tree", "deps list",
        "---",
        "publish validate",
    ],
    "gem": [
        "gem info",
        "---",
        "deps tree", "deps list",
        "---",
        "publish validate",
    ],
    "template": [
        "template create", "template instance",
        "---",
        "template info",
        "---",
        "publish validate",
    ],
    "repo": [
        "repo create",
    ],
    "overlay": [
        "overlay create",
        "---",
        "publish validate",
    ],
    # Fallback for any unrecognised type
    "_default": [
        "deps tree", "deps list",
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_commands_for_group(group_id: str) -> list[dict | None]:
    """Return command specs for a toolbar group.

    Items can be:
    - ``None`` → separator
    - a command spec ``dict`` → flat action
    - ``{"submenu": label, "items": [spec, ...]}`` → nested submenu
    """
    for g in TOOLBAR_GROUPS:
        if g["id"] == group_id:
            result: list[dict | None] = []
            for entry in g["commands"]:
                if entry == "---":
                    result.append(None)
                elif isinstance(entry, dict) and "submenu" in entry:
                    # Build a submenu descriptor
                    sub_specs = []
                    for cmd_key in entry["items"]:
                        if cmd_key == "---":
                            sub_specs.append(None)
                        else:
                            sub_specs.append(COMMAND_SPECS.get(cmd_key))
                    result.append({
                        "submenu": entry["submenu"],
                        "items": sub_specs,
                    })
                else:
                    result.append(COMMAND_SPECS.get(entry))
            return result
    return []


def get_context_commands(object_type: str) -> list[dict | None]:
    """Return command specs for a context-menu given an object type value."""
    keys = CONTEXT_MENU_COMMANDS.get(
        object_type, CONTEXT_MENU_COMMANDS["_default"]
    )
    result = []
    for k in keys:
        if k == "---":
            result.append(None)
        else:
            result.append(COMMAND_SPECS.get(k))
    return result
