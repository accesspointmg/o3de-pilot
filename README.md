# O3DE Pilot

> ⚠️ **Early Development** - This project is under active development and not yet ready for production use. APIs and features may change without notice.

**AI-powered replacement for O3DE Project Manager.** CLI-first architecture with npm-style package management for the O3DE ecosystem. Future O3DE Foundation contribution.

## Vision

O3DE Pilot aims to modernize how developers interact with the O3DE ecosystem by providing:

- 🖥️ **CLI-First Design** - Scriptable, automatable, GUI is optional
- 📦 **npm-Style Package Management** - Familiar workflow for gems, templates, projects, and engines
- 🤖 **Pluggable AI Assistance** - Choose your provider (Claude, Ollama, OpenAI, local LLMs)
- 🌐 **Community Registry** - Discover and install community packages easily
- 🔌 **Standalone Operation** - No engine installation required to run

## Current Status

**v0.1.0** — O3DE Pilot ships as two packages:

| Package | Repo | Provides | Source | Tests |
|---|---|---|---|---|
| `o3de-cli` | [accesspointmg/o3de-cli](https://github.com/accesspointmg/o3de-cli) | `o3de` CLI, `o3de-mcp` MCP server | 39 files | 40 files, 1126 tests |
| `o3de-pilot` | this repo (`src/gui`) | `o3de-pilot` Qt6 GUI | 32 files | 5 files, 191 tests |

The GUI depends on the CLI (`o3de-cli>=0.1.0`), which holds the package-management
core. Install the CLI on its own if you don't need the GUI.

### Implemented Features

| Area | Status | Details |
|------|--------|--------|
| Manifest Resolution | ✅ Complete | Full DAG resolution, parent-child chains, overlay matching |
| Dependency Management | ✅ Complete | Lock file, conflict detection, optional/peer deps, transitive pinning |
| Integrity Verification | ✅ Done | SHA-256 extracted from release metadata and verified on download |
| Auto-Install | ✅ Done | `manifest resolve --install [--yes]` fetches missing deps from remotes |
| Schema 2.0.0 | ✅ Complete | Auto-upgrade 0→1→2, versioned filenames, reverse domain names |
| Registry / Store | ✅ Complete | Remote fetch, caching, git clone + zip download, search |
| Layout Engine | ✅ Complete | Symlink-based build directories with overlay support (via workspace) |
| Hooks Engine | ✅ Complete | Pre/post install scripts with confirmation, timeout, dry-run |
| Publish / Validate | ✅ Done | JSON Schema validation, pack, push with version immutability |
| Audit | ✅ Complete | Scan for deprecated objects, missing integrity, conflicts |
| Workspace | ✅ Complete | Multi-project coordination, create→resolve→assemble→build |
| Dependency Tree | ✅ Complete | `deps tree/list/why` with Rich visualization |
| Solver | ✅ Complete | resolvelib-based dependency solver with backtracking |
| Build Integration | ✅ Complete | CMake configure/build/install with preset support |
| GUI | ✅ Complete | PySide6/Qt6 catalog with async icons, filters, inspector, AI tab, workspace solver |
| AI Assistance | ✅ Complete | Multi-provider (Claude/Ollama/OpenAI), agent with tool loop. Exposed via the GUI's AI tab and the `o3de mcp` server — no `o3de ai` command group |
| Auth & Registry | ✅ Complete | Token-based auth, login/logout/whoami, lockfiles |
| Policy Enforcement | ✅ Complete | License compliance, security advisories, deprecation checks |

## CLI Reference

The command is `o3de` (installed by the `o3de-cli` package). `o3de-pilot` is the
GUI entrypoint and takes no subcommands — use `o3de gui` or plain `o3de-pilot`.

```bash
# Manifest & Resolution
o3de manifest resolve               # Resolve manifest into dependency-locked snapshot
o3de manifest show                  # Show current manifest
o3de manifest upgrade               # Upgrade legacy schema files to 2.0.0
o3de manifest add|remove <path>     # Add / remove object path
o3de manifest get|set <key> [value]  # Read / write a manifest field

# Registry / Discovery
o3de search <query>                 # Search remote registries
o3de install <package>              # Install a gem, template, or package
o3de list projects|gems|templates|engines   # List registered objects (type required)
o3de registry refresh|update        # Refresh remote repo data / re-resolve latest
o3de registry install <url>         # Install from URL
o3de registry uninstall <name>      # Remove cached remote objects
o3de registry add-remote|remove-remote|list-remotes
o3de registry login|logout|whoami   # Token-based auth

# Object Management
o3de repo create|list|register|unregister
o3de gem create|info|list|register|search|unregister
o3de project add|build|init|list|register|run|unregister
o3de template create|info|instance|list|register|unregister
o3de engine create|list|register|unregister
o3de overlay create|list|register|unregister
o3de register <path-or-url>         # Register any object type
o3de unregister <path-or-name>
o3de init <name>                    # Initialize a new project

# Binary Objects
o3de object build|install|package|hoist|split-platforms

# Dependency Management
o3de deps tree [name]               # Visualize dependency tree (Rich formatted)
o3de deps list [name]               # List direct/transitive/optional/peer deps
o3de deps why <from> <to>           # Find shortest dependency chain between objects

# Publishing & Validation
o3de publish validate <path>        # Validate object JSON against 2.0.0 schema
o3de publish pack <path>            # Pack an object for distribution
o3de publish push <path>            # Validate + publish to remote repo

# Audit
o3de audit                          # Scan for deprecated objects, missing integrity, conflicts
o3de audit --fix                    # Auto-fix issues where possible
o3de audit --json                   # Machine-readable output

# Workspace
o3de workspace create <name>        # Create a multi-project workspace
o3de workspace show|list|tree       # Inspect workspace state
o3de workspace solve|candidates     # Run the dependency solver
o3de workspace lock|verify-lock     # Write / check the lock file
o3de workspace build|update|override|delete

# Configuration
o3de config get|set|unset|list|path

# GUI & AI
o3de gui                            # Launch Qt6 graphical interface
o3de mcp                            # Start MCP server on stdio (also: o3de-mcp)
```

AI assistance is available through the GUI's AI tab and through the `mcp` server;
there is no `o3de ai` command group.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│           o3de-pilot  —  GUI (PySide6/Qt6)              │
│      this repo, src/gui/o3de_pilot_gui                  │
│  Catalog · Inspector · Filters · Workspace · AI tab     │
└─────────────────────────┬───────────────────────────────┘
                          │ depends on o3de-cli>=0.1.0
                          ▼
┌─────────────────────────────────────────────────────────┐
│            o3de-cli  —  Python CLI Core                 │
│     separate repo · commands: o3de, o3de-mcp            │
├─────────────┬───────────┬───────────┬───────────────────┤
│  Commands   │   Core    │   Tests   │   AI / MCP        │
│ (22 groups) │           │  (1126)   │                   │
├─────────────┼───────────┼───────────┼───────────────────┤
│ manifest    │ resolver  │ models    │ Claude/Opus       │
│ registry    │ store     │ resolver  │ Ollama            │
│ repo/overlay│ layout    │ store     │ OpenAI            │
│ gem/project │ models    │ layout    │ Local LLMs        │
│ engine/tmpl │ upgrade   │ upgrade   │ MCP server        │
│ publish     │ hooks     │ paths     │   (o3de mcp)      │
│ audit       │ paths     │ commands  │                   │
│ workspace   │ config    │ git_utils │                   │
│ deps        │ network   │ config    │                   │
│ object      │ git_utils │ hooks     │                   │
│ config      │ auth      │ policy    │                   │
│ gui/mcp     │ lockfile  │ e2e       │                   │
└─────────────┴───────────┴───────────┴───────────────────┘
        │                 │
        ▼                 ▼
┌───────────────┐ ┌───────────────┐
│   Registry    │ │  Local Store  │
│  (Community)  │ │ (~/.o3de)     │
├───────────────┤ ├───────────────┤
│ • Gems        │ │ • Manifest    │
│ • Templates   │ │ • Lock file   │
│ • Projects    │ │ • Cache       │
│ • Engines     │ │ • Layouts     │
└───────────────┘ └───────────────┘
```

## Getting Started

### Installation

The CLI and GUI live in separate repositories. Clone both as siblings:

```bash
git clone https://github.com/accesspointmg/o3de-cli.git
git clone https://github.com/accesspointmg/o3de-pilot.git
cd o3de-pilot

# Recommended: an isolated environment
python3 -m venv .venv && source .venv/bin/activate

# Install both in development mode (GUI's pyproject.toml lives in src/gui)
pip install -e ../o3de-cli -e src/gui

# Verify installation
o3de --version      # CLI
o3de-pilot          # launches the GUI
```

To install the CLI alone, `pip install -e ../o3de-cli` is sufficient — it pulls in
no Qt dependency.

### Dependencies

- Python 3.10+ (3.13 recommended)
- Click (CLI framework)
- Pydantic v2 (data models)
- Rich (terminal formatting)
- httpx (HTTP client)
- PyYAML (configuration)
- PySide6 (GUI, optional)
- packaging (version specifiers)

### Basic Usage

```bash
# Resolve manifest — discovers all registered objects, builds dependency graph
o3de manifest resolve

# List discovered objects (the type argument is required)
o3de list gems
o3de list projects
o3de list engines
o3de repo list

# Visualize dependency tree
o3de deps tree

# Search remote registries
o3de search atoms

# Install a gem from remote
o3de install org.o3de.gem.atoms

# Audit your dependency tree
o3de audit

# Create a new project from template
o3de project init my-game --template DefaultProject

# Create a symlinked build workspace
o3de workspace create my-workspace

# Launch the GUI
o3de gui
```

### Configuration

```bash
# List all configuration
o3de config list

# Set AI provider
o3de config set ai.provider ollama
o3de config set ai.model llama3
o3de config get ai.provider
```

Recognized keys: `ai.provider`, `ai.model`, `ai.api_key`, `ai.ollama_url`,
`registry.url`, `manifest.path`.

### Running Tests

Each package has its own suite. Qt tests need a display; use the offscreen
platform plugin on headless machines.

```bash
export QT_QPA_PLATFORM=offscreen

# GUI tests (this repo) — 191 collected
pip install -e "src/gui[dev]"
python -m pytest tests/ -v

# CLI tests — 1126 collected
pip install -e "../o3de-cli[dev]"
python -m pytest ../o3de-cli/tests/ -v
```

> **Known failures.** Both suites currently have failures on `main` (GUI 37,
> CLI 34 as of this writing). The GUI failures all stem from the AI tests
> patching an `o3de_cli.ai` module that no longer exists
> (`AttributeError: module 'o3de_cli' has no attribute 'ai'`); the CLI failures
> are concentrated in the workspace, upgrade, and object-hoist tests. These are
> tracked separately — a clean run is not yet the baseline.

## Schema 2.0.0

O3DE Pilot introduces Schema 2.0.0 for O3DE object metadata files:

- **Versioned filenames**: `engine.2-0-0.json` preferred over `engine.json`
- **Explicit JSON paths**: Children use full paths like `Gems/MyGem/gem.json`
- **Reverse domain names**: Objects use names like `org.o3de.gem.atoms`
- **Auto-upgrade**: Legacy files automatically upgraded during resolution
- **Integrity fields**: SHA-256 checksums on releases/downloads
- **Optional/peer dependencies**: npm-style dependency semantics
- **Deprecation metadata**: Objects can declare deprecation with replacement suggestions
- **Hooks**: Pre/post install scripts with security confirmation

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md)
before getting started.

O3DE Pilot follows the same branching and release model used across the O3DE
family of repositories:

- **[Branching Model](docs/branching-model.md)** — `main` / `development` /
  `stabilization/YYMM` branch architecture and protection rules.
- **[Release Process](docs/release-process.md)** — How stabilization branches
  are cut, how the semver is determined, and how releases are built and
  published.
- **[Contributing Guide](CONTRIBUTING.md)** — Fork-based workflow, PR gating,
  DCO requirements, and coding standards.

All contributors must adhere to our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

This project is dual-licensed under the Apache License 2.0 and MIT License. See [LICENSE.txt](LICENSE.txt) for details.

## Acknowledgments

- [Open 3D Engine](https://o3de.org) - The foundation this project builds upon
- [O3DE Foundation](https://o3de.org) - Intended future home of this project
