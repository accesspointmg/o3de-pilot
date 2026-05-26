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

**v0.1.0** — 55 source files (~21.5k lines), 31 test files (~8.8k lines), **770 tests passing**.

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
| Publish / Validate | ✅ Done | JSON Schema validation against canonical 2.0.0 schemas + structural checks |
| Audit | ✅ Complete | Scan for deprecated objects, missing integrity, conflicts |
| Workspace | ✅ Complete | Multi-project workspace coordination |
| Dependency Tree | ✅ Complete | `deps tree/list/why` with Rich visualization |
| Solver | ✅ Complete | resolvelib-based dependency solver with backtracking |
| GUI | ✅ Complete | PySide6/Qt6 catalog with async icons, filters, inspector, AI tab, workspace solver |
| AI Assistance | 🔧 Basic | Provider framework wired, `ask` functional, other commands basic |
| Project Build/Run | 🔧 Basic | CMake invocation, executable launch |

## CLI Reference

```bash
# Manifest & Resolution
o3de-pilot manifest resolve         # Resolve manifest into dependency-locked snapshot
o3de-pilot manifest show            # Show current manifest
o3de-pilot manifest upgrade         # Upgrade legacy schema files to 2.0.0
o3de-pilot manifest add <path>      # Add object path to manifest
o3de-pilot manifest remove <path>   # Remove object path from manifest

# Registry / Discovery
o3de-pilot search <query>           # Search remote registries
o3de-pilot install <package>        # Install a gem, template, or package
o3de-pilot list                     # List registered objects
o3de-pilot registry refresh         # Refresh remote repo data
o3de-pilot registry install <url>   # Install from URL
o3de-pilot registry uninstall <name> # Remove cached remote objects
o3de-pilot registry update          # Refresh + re-resolve with latest versions

# Object Management
o3de-pilot gem list|create|info|search
o3de-pilot project list|init|build|run|add
o3de-pilot template list|info
o3de-pilot engine list|register|unregister

# Dependency Management
o3de-pilot deps tree [name]         # Visualize dependency tree (Rich formatted)
o3de-pilot deps list [name]         # List direct/transitive/optional/peer deps
o3de-pilot deps why <from> <to>     # Find shortest dependency chain between objects

# Publishing & Validation
o3de-pilot publish validate <path>  # Validate object JSON against 2.0.0 schema
o3de-pilot publish push <path>      # Validate + publish to remote repo

# Audit
o3de-pilot audit                    # Scan for deprecated objects, missing integrity, conflicts
o3de-pilot audit --fix              # Auto-fix issues where possible
o3de-pilot audit --json             # Machine-readable output

# Workspace
o3de-pilot workspace init <name>    # Initialize multi-project workspace
o3de-pilot workspace status         # Show workspace state
o3de-pilot workspace add-project <path>
o3de-pilot workspace set-engine <path>
o3de-pilot workspace add-gem <name>

# Layout
o3de-pilot layout create|list|show|delete|tree

# Configuration
o3de-pilot config get|set|unset|list|path

# AI-Assisted
o3de-pilot ai ask <question>        # Ask AI for help
o3de-pilot ai diagnose              # AI analyzes build errors
o3de-pilot ai generate              # AI-assisted code generation
o3de-pilot ai migrate               # AI-assisted upgrades
o3de-pilot ai explain               # Explain code/concepts

# GUI
o3de-pilot gui                      # Launch Qt6 graphical interface
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   GUI (PySide6/Qt6)                     │
│        Catalog · Inspector · Filters · Downloads        │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   Python CLI Core                       │
│                    (o3de-pilot)                         │
├─────────────┬───────────┬───────────┬───────────────────┤
│  Commands   │   Core    │   Tests   │   AI Providers    │
│  (12 groups)│           │ (770)     │                   │
├─────────────┼───────────┼───────────┼───────────────────┤
│ manifest    │ resolver  │ models    │ Claude/Opus       │
│ registry    │ store     │ resolver  │ Ollama            │
│ gem/project │ layout    │ store     │ OpenAI            │
│ engine/tmpl │ models    │ layout    │ Local LLMs        │
│ publish     │ upgrade   │ upgrade   │                   │
│ audit       │ hooks     │ paths     │                   │
│ workspace   │ paths     │ commands  │                   │
│ deps        │ config    │ git_utils │                   │
│ layout      │ network   │ config    │                   │
│ config/ai   │ git_utils │ hooks     │                   │
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

```bash
# Clone the repository
git clone https://github.com/byrcolin/o3de-pilot.git
cd o3de-pilot/src/cli

# Install in development mode
pip install -e .

# Verify installation
o3de-pilot --version
```

### Dependencies

- Python 3.10+
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
o3de-pilot manifest resolve

# List discovered objects
o3de-pilot gem list
o3de-pilot project list
o3de-pilot engine list

# Visualize dependency tree
o3de-pilot deps tree

# Search remote registries
o3de-pilot search atoms

# Install a gem from remote
o3de-pilot install org.o3de.gem.atoms

# Audit your dependency tree
o3de-pilot audit

# Create a new project from template
o3de-pilot project init my-game --template DefaultProject

# Create a symlinked build layout
o3de-pilot layout create my-layout

# Launch the GUI
o3de-pilot gui
```

### Configuration

```bash
# List all configuration
o3de-pilot config list

# Set AI provider
o3de-pilot config set ai.provider ollama
o3de-pilot config set ai.model llama3
o3de-pilot config get ai.provider
```

### Running Tests

```bash
cd o3de-pilot
pip install pytest
python -m pytest src/cli/tests/ -v
# 770 passed
```

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

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) before getting started.

All contributors must adhere to our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

This project is dual-licensed under the Apache License 2.0 and MIT License. See [LICENSE.txt](LICENSE.txt) for details.

## Acknowledgments

- [Open 3D Engine](https://o3de.org) - The foundation this project builds upon
- [O3DE Foundation](https://o3de.org) - Intended future home of this project
