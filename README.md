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

## Planned Features

```bash
# Registry / Discovery
o3de-pilot search <query>           # Search community registry
o3de-pilot info <package>           # Package details
o3de-pilot list                     # List installed objects

# Installation
o3de-pilot install <gem>            # Install a gem
o3de-pilot install <template>       # Install a template
o3de-pilot update <package>         # Update package
o3de-pilot uninstall <package>      # Remove package

# Project Management
o3de-pilot init <project>           # Create new project
o3de-pilot add gem <name>           # Add gem to project
o3de-pilot build                    # Build project
o3de-pilot run                      # Run project

# AI-Assisted
o3de-pilot ai ask how do I ...      # Ask AI for help
o3de-pilot ai create a new project that...
o3de-pilot ai create a gem that...  # AI-assisted o3de generation
o3de-pilot ai diagnose build errors # AI analyzes build errors
o3de-pilot ai fix build errors      # AI assisted build error fix
o3de-pilot ai migrate gem           # AI-assisted upgrades
o3de-pilot ai find a grass texture  # AI-assisted asset search
o3de-pilot ai create grass material
o3de-pilot ai create entity         # Ai-assisted editor automation
o3de-pilot ai move entity <id/name/description> to...
o3de-pilot ai rotate entity 30 degrees to the right
o3de-pilot ai add component to entity
o3de-pilot ai analyses scene

# Configuration
o3de-pilot config set ai.provider ollama
o3de-pilot config set ai.model llama3
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                      GUI (Optional)                      │
│                 (Issues CLI commands only)               │
└─────────────────────────┬───────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│                   Python CLI Core                        │
│                    (o3de-pilot)                          │
├─────────────────────────────────────────────────────────┤
│  • Registry/Package Management                          │
│  • Project/Gem/Template CRUD                            │
│  • Dependency Resolution                                │
│  • Build Orchestration                                  │
│  • AI Adapter Layer                                     │
└───────┬─────────────────┬─────────────────┬─────────────┘
        │                 │                 │
        ▼                 ▼                 ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│   Registry    │ │  Local Store  │ │  AI Providers │
│  (Community)  │ │ (~/.o3de)     │ │               │
├───────────────┤ ├───────────────┤ ├───────────────┤
│ • Gems        │ │ • Projects    │ │ • Claude/Opus │
│ • Templates   │ │ • Gems        │ │ • Ollama      │
│ • Projects    │ │ • Engines     │ │ • OpenAI      │
│ • Engines     │ │ • Cache       │ │ • Local LLMs  │
└───────────────┘ └───────────────┘ └───────────────┘
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

### Basic Usage

```bash
# Initialize user directories (~/.o3de and ~/O3DE)
o3de-pilot init

# Resolve manifest and list all discovered objects
o3de-pilot manifest resolve

# List installed gems/projects/templates
o3de-pilot gem list
o3de-pilot project list
o3de-pilot template list

# Create a layout (symlinked build directory)
o3de-pilot layout create my-layout

# Remote package management
o3de-pilot registry refresh      # Fetch remote repo data
o3de-pilot registry search atoms # Search for packages
o3de-pilot registry install <url> # Install from remote
```

### Configuration

```bash
# List all configuration
o3de-pilot config list

# Set configuration values
o3de-pilot config set ai.provider ollama
o3de-pilot config get ai.provider
```

### Running Tests

```bash
cd src/cli
pip install pytest
python -m pytest tests/ -v
```

## Schema 2.0.0

O3DE Pilot introduces Schema 2.0.0 for O3DE object metadata files:

- **Versioned filenames**: `engine.2-0-0.json` preferred over `engine.json`
- **Explicit JSON paths**: Children use full paths like `Gems/MyGem/gem.json`
- **Reverse domain names**: Objects use names like `org.o3de.gem.atoms`
- **Auto-upgrade**: Legacy files automatically upgraded during resolution

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) before getting started.

All contributors must adhere to our [Code of Conduct](CODE_OF_CONDUCT.md).

## License

This project is dual-licensed under the Apache License 2.0 and MIT License. See [LICENSE.txt](LICENSE.txt) for details.

## Acknowledgments

- [Open 3D Engine](https://o3de.org) - The foundation this project builds upon
- [O3DE Foundation](https://o3de.org) - Intended future home of this project
