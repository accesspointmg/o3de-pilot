# Contributing to O3DE Pilot

Welcome to O3DE Pilot! We're excited that you're interested in contributing. This document provides guidelines and information about contributing to this project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Commit Messages](#commit-messages)
- [License](#license)

## Code of Conduct

Please review our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR-USERNAME/o3de-pilot.git
   cd o3de-pilot
   ```
3. **Add the upstream remote**:
   ```bash
   git remote add upstream https://github.com/byrcolin/o3de-pilot.git
   ```
4. **Create a branch** for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## How to Contribute

### Reporting Bugs

- Check if the bug has already been reported in [Issues](https://github.com/byrcolin/o3de-pilot/issues)
- If not, create a new issue using the Bug Report template
- Provide as much detail as possible

### Suggesting Features

- Check existing issues and discussions for similar suggestions
- Create a new issue using the Feature Request template
- Describe the feature and its use case

### Code Contributions

1. Find an issue to work on, or create one
2. Comment on the issue to let others know you're working on it
3. Follow the development setup and coding standards below
4. Submit a pull request

## Development Setup

### Prerequisites

- Python 3.10+
- Git

### Installation

```bash
# Clone the repo
git clone https://github.com/YOUR-USERNAME/o3de-pilot.git
cd o3de-pilot

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies (when available)
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=o3de_pilot
```

## Pull Request Process

1. **Update your branch** with the latest upstream changes:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Ensure all tests pass** and add new tests for new functionality

3. **Update documentation** if needed

4. **Sign your commits** using the DCO (Developer Certificate of Origin):
   ```bash
   git commit -s -m "Your commit message"
   ```

5. **Push your branch** and create a pull request:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Fill out the PR template** completely

7. **Address review feedback** promptly

## Coding Standards

### Python Style

- Follow [PEP 8](https://pep8.org/) style guide
- Use type hints for function parameters and return values
- Maximum line length: 120 characters
- Use meaningful variable and function names

### Code Organization

- Keep functions focused and small
- Write docstrings for public functions and classes
- Organize imports: stdlib, third-party, local

### Example

```python
"""Module description."""
from typing import Optional

import click

from o3de_pilot.core import registry


def install_gem(name: str, version: Optional[str] = None) -> bool:
    """
    Install a gem from the registry.

    Args:
        name: The name of the gem to install.
        version: Optional specific version to install.

    Returns:
        True if installation succeeded, False otherwise.
    """
    # Implementation
    pass
```

## Commit Messages

Follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting, semicolons, etc.)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

### Examples

```
feat(cli): add gem install command
fix(registry): handle network timeout errors
docs(readme): update installation instructions
```

## Developer Certificate of Origin (DCO)

All commits require the DCO sign-off. This certifies that you have the right to submit the code under the project's license.

Sign your commits with:
```bash
git commit -s -m "Your commit message"
```

This adds a `Signed-off-by` line to your commit message.

## License

By contributing to O3DE Pilot, you agree that your contributions will be licensed under the project's dual Apache 2.0 / MIT license.

## Questions?

Feel free to open a [Discussion](https://github.com/byrcolin/o3de-pilot/discussions) or reach out to the maintainers.

Thank you for contributing! 🚀
