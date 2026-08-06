# Contributing to O3DE Pilot

Welcome to O3DE Pilot! We're excited that you're interested in contributing.
This document describes how we work, how to set up your environment, and how
to get your changes merged.

O3DE Pilot follows the same branching and contribution model used across the
[Open 3D Engine](https://o3de.org) family of repositories. If you've
contributed to O3DE before, this will feel familiar.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Branching Model](#branching-model)
- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Pull Request Process](#pull-request-process)
- [PR Gating (Automated Review)](#pr-gating-automated-review)
- [Coding Standards](#coding-standards)
- [Commit Messages](#commit-messages)
- [Developer Certificate of Origin (DCO)](#developer-certificate-of-origin-dco)
- [Release Process](#release-process)
- [License](#license)

## Code of Conduct

Please review our [Code of Conduct](CODE_OF_CONDUCT.md) before contributing.

## Branching Model

O3DE Pilot uses a two-branch model with stabilization branches for releases.
For the full picture see [docs/branching-model.md](docs/branching-model.md).

| Branch | Protected | Purpose |
|---|---|---|
| `main` | Yes | Release-quality code. Only receives merges from `stabilization/*` branches. |
| `development` | Yes | Integration branch. All contributor PRs target this branch. |
| `stabilization/YYMM` | Soft | Cut from `development` when a release window opens. Receives only targeted fixes. |
| Feature branches (on forks) | No | Your day-to-day work. Branched from `development`. |

**Key rules:**

- Contributors **never push directly** to `main` or `development`.
- All changes reach `development` through pull requests from forks.
- All changes reach `main` through stabilization branches.

## Getting Started

### 1. Fork the repository on GitHub

Click the **Fork** button on the [o3de-pilot](https://github.com/accesspointmg/o3de-pilot)
repository page.

### 2. Clone your fork

```bash
git clone https://github.com/<your-username>/o3de-pilot.git
cd o3de-pilot
```

### 3. Set the upstream remote

```bash
git remote add upstream https://github.com/accesspointmg/o3de-pilot.git
git fetch upstream
```

### 4. Create a feature branch from `development`

```bash
git checkout -b feature/my-feature upstream/development
```

Always branch from `upstream/development`, **not** from `main`.

## How to Contribute

### Reporting Bugs

- Check if the bug has already been reported in
  [Issues](https://github.com/accesspointmg/o3de-pilot/issues)
- If not, create a new issue using the **Bug Report** template
- Provide as much detail as possible

### Suggesting Features

- Check existing issues and discussions for similar suggestions
- Create a new issue using the **Feature Request** template
- Describe the feature and its use case

### Code Contributions

1. Find an issue to work on, or create one
2. Comment on the issue to let others know you're working on it
3. Follow the development setup and coding standards below
4. Submit a pull request **against `development`**

## Development Setup

### Prerequisites

- Python 3.10+ (3.13 recommended)
- Git

### Installation

```bash
# Clone your fork and set upstream (see Getting Started above)
cd o3de-pilot

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install both packages in development mode
pip install -e ../o3de-cli -e "src/gui[dev]"
```

### Running Tests

```bash
# GUI tests (this repo) — needs QT_QPA_PLATFORM=offscreen on headless
export QT_QPA_PLATFORM=offscreen
python -m pytest tests/ -v

# CLI tests (sibling repo)
python -m pytest ../o3de-cli/tests/ -v

# With coverage
python -m pytest tests/ --cov=o3de_pilot_gui
```

## Pull Request Process

### 1. Keep your branch up to date

```bash
git fetch upstream
git rebase upstream/development
```

### 2. Sign every commit (DCO)

```bash
git commit -s -m "feat(cli): add gem install command"
```

See [Developer Certificate of Origin](#developer-certificate-of-origin-dco)
below.

### 3. Push to your fork and open a PR

```bash
git push origin feature/my-feature
```

Open the PR **against the `development` branch** on the upstream repository.
Do not target `main`.

### 4. Pass automated checks

The following checks run automatically on every PR to `development`:

- **DCO sign-off** — every commit must have a `Signed-off-by` line
- **Lint & format** — Ruff linter and formatter
- **Type check** — MyPy
- **Tests** — pytest suite must pass

All checks must be green before a maintainer can merge.

### 5. Human review

At least one maintainer must approve the PR. Reviewers may request changes;
please address feedback promptly. Stale approvals are dismissed when new
commits are pushed.

### 6. Fill out the PR template completely

### 7. Merge

Once approved and all checks pass, a maintainer will merge the PR into
`development`.

## PR Gating (Automated Review)

PRs against `development` must pass all of the following before merge is
allowed:

| Check | Tool | Blocking |
|---|---|---|
| DCO sign-off | `dco-check` | Yes |
| Lint | `ruff check` | Yes |
| Format | `ruff format --check` | Yes |
| Type check | `mypy` | Yes |
| Tests | `pytest` | Yes |
| Maintainer approval | GitHub CODEOWNERS | Yes (1+ approvals) |

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

Follow the [Conventional Commits](https://www.conventionalcommits.org/)
specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]

Signed-off-by: Your Name <your@email.com>
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

All commits must carry a DCO sign-off. This certifies that you have the right
to submit the code under the project's license.

Sign your commits with the `-s` flag:

```bash
git commit -s -m "Your commit message"
```

This appends a `Signed-off-by: Your Name <your@email.com>` line to the commit
message using the name and email from your Git configuration. The DCO check in
CI will reject commits that are missing this line.

If you forgot to sign off on earlier commits in a branch you can amend them:

```bash
# Amend the last commit
git commit --amend -s --no-edit

# Rebase and sign off on all commits in the branch
git rebase --signoff upstream/development
```

## Release Process

Releases follow the O3DE stabilization-branch model. The full process is
documented in [docs/release-process.md](docs/release-process.md). In short:

1. `development` accumulates features via contributor PRs.
2. When enough work has landed, a `stabilization/YYMM` branch is cut from
   `development`.
3. The stabilization branch receives only targeted fixes.
4. At the end of stabilization the team determines the semver bump.
5. The stabilization branch is merged into `main` and tagged (e.g., `v0.1.0`).
6. CI builds and publishes release artifacts from the tag on `main`.
7. The stabilization branch is back-merged into `development` and deleted.

See also: [docs/branching-model.md](docs/branching-model.md)

## License

By contributing to O3DE Pilot, you agree that your contributions will be
licensed under the project's dual Apache 2.0 / MIT license.
See [LICENSE.txt](LICENSE.txt) for details.

## Questions?

Feel free to open a
[Discussion](https://github.com/accesspointmg/o3de-pilot/discussions)
or reach out to the maintainers.

Thank you for contributing!
