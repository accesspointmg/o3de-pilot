# Release Process

O3DE Pilot follows the release model used across the
[Open 3D Engine](https://o3de.org) family of repositories. This document
describes every phase of a release from start to finish.

## Overview

```
1. Development accumulates on the 'development' branch via contributor PRs.
2. The team agrees enough work has landed to justify a release.
3. A stabilization branch is cut from 'development'.
4. The stabilization branch is hardened with targeted fixes only.
5. The team reviews the full delta and determines the semver bump.
6. The stabilization branch is merged into 'main' and tagged.
7. CI builds release artifacts from the tag on 'main'.
8. The stabilization branch is back-merged into 'development' and deleted.
```

## Versioning

O3DE Pilot uses two complementary identifiers:

| Identifier | When it is known | Format | Example | Purpose |
|---|---|---|---|---|
| Release number | When stabilization begins | `YYMM` | `2507` | Branch naming, internal tracking |
| Semver | When stabilization ends | `MAJOR.MINOR.PATCH` | `0.2.0` | Public version, package version, Git tag |

The release number is derived from the date the stabilization branch is cut,
following the `YYMM` format (e.g., `2507` for July 2025), similar to how Linux
distributions derive release numbers from dates.

The semver **cannot be known** when the stabilization branch is created because
the team has not yet reviewed the full set of changes or finished stabilization
fixes. It is determined at the end of stabilization.

### Semver Rules

[Semantic Versioning 2.0.0](https://semver.org/) is used:

| Change type | Bump | Example |
|---|---|---|
| Breaking changes to API, config format, or CLI interface | **MAJOR** | `0.2.0` -> `1.0.0` |
| New features, all backward-compatible | **MINOR** | `0.1.0` -> `0.2.0` |
| Bug fixes only, no new features | **PATCH** | `0.1.0` -> `0.1.1` |

Pre-release versions are supported: `1.0.0-alpha.1`, `1.0.0-beta.1`,
`1.0.0-rc.1`.

---

## Phase 1: Decide to Release

**Trigger:** The team agrees that enough features, fixes, or improvements have
accumulated on `development` to justify sharing them with users of the
released version.

There is no fixed cadence. Releases happen when the work justifies one.

| Release type | Typical frequency | Notes |
|---|---|---|
| Feature release | Every 4-6 weeks | Tied to milestone completion |
| Patch release | As needed | Critical fixes, can release same-day |
| Major release | As needed | Breaking changes, architectural shifts |

## Phase 2: Cut the Stabilization Branch

The release maintainer creates the stabilization branch from the current tip
of `development`. The branch name uses the release number.

```bash
# Derive the release number from the current date.
# July 2025 -> 2507

git fetch upstream
git checkout -b stabilization/2507 upstream/development
git push upstream stabilization/2507
```

From this point forward:

- **`development` stays open** for new feature work toward the *next* release.
- **`stabilization/2507`** is frozen to new features. It only accepts targeted
  bug fixes and documentation updates.

## Phase 3: Stabilize

During stabilization the team focuses on hardening the release:

- Run the full test matrix across all supported platforms (macOS, Windows,
  Ubuntu, Fedora).
- Fix bugs found during stabilization. Fixes are submitted as PRs targeting
  `stabilization/2507`.
- Update documentation as needed.
- **No new features are allowed on the stabilization branch.**

## Phase 4: Determine the Semver

At the end of stabilization, the team reviews every change since the last
release:

```bash
# Find the last release tag
git describe --tags --abbrev=0
# -> v0.1.0

# Review the full delta
git log v0.1.0..stabilization/2507 --oneline
```

The team applies the [semver rules](#semver-rules) to determine whether the
release is a MAJOR, MINOR, or PATCH bump.

## Phase 5: Apply the Version and Finalize

Once the semver is determined, the release maintainer sets the version in all
relevant files and finalizes the changelog.

```bash
git checkout stabilization/2507

# 1. Set the version in pyproject.toml (or wherever the version lives)
#    version = "0.2.0"

# 2. Finalize CHANGELOG.md
#    - Move the [Unreleased] section contents under the new version header
#    - Add the release date and release number
#    - Example: ## [0.2.0] - 2025-07-28 (Release 2507)

# 3. Commit
git commit -s -m "release: set version 0.2.0 (release 2507)"
git push upstream stabilization/2507
```

## Phase 6: Merge to Main and Tag

The stabilization branch is merged into `main` via a pull request for audit
trail purposes. After the merge, the release is tagged.

```bash
# Open a PR: stabilization/2507 -> main
# Title: "Release 0.2.0 (release 2507)"
# The PR must pass all CI checks.
# A release maintainer merges the PR.

# After the merge, tag the release on main.
git fetch upstream
git checkout upstream/main
git tag -a v0.2.0 -m "Release 0.2.0 (release 2507)"
git push upstream v0.2.0
```

## Phase 7: Build and Publish

Pushing the tag triggers the release CI workflow
(`.github/workflows/release.yml`), which:

1. Validates the version format and checks for duplicate tags.
2. Builds platform binaries (macOS DMG, Windows EXE, Linux binary).
3. Builds the Python package (`sdist` and `wheel`).
4. Creates a GitHub Release with auto-generated release notes and uploads all
   artifacts.

Release artifacts:

| Artifact | Description |
|---|---|
| GitHub Release | Tagged release with changelog, platform binaries |
| Python package | `pip install o3de-pilot` (PyPI, when configured) |
| macOS DMG | Universal binary for macOS |
| Windows EXE | x64 executable |
| Linux binary | x86_64 binary (Ubuntu, Fedora) |

## Phase 8: Post-Release

### Back-merge into development

Stabilization fixes must not be lost. The stabilization branch is merged back
into `development`:

```bash
git fetch upstream
git checkout development
git merge upstream/stabilization/2507
git push upstream development
```

### Delete the stabilization branch

The stabilization branch has served its purpose:

```bash
git push upstream --delete stabilization/2507
```

### Bump the development version (optional)

If the team wants to clearly mark development as targeting the next release,
the version on `development` can be bumped to a dev suffix:

```bash
# version = "0.3.0.dev0"
```

---

## Release Checklist

This is the complete checklist for a release maintainer. Copy this into the
stabilization PR or a tracking issue.

### Pre-stabilization

- [ ] Team agrees that enough work has landed on `development`
- [ ] All blocking issues for this release are resolved
- [ ] CI is green on `development`

### Cut stabilization

- [ ] Branch `stabilization/YYMM` from `development`
- [ ] Announce to contributors that `development` is open for next-release work

### Stabilization

- [ ] Full test matrix passes (macOS, Windows, Ubuntu, Fedora)
- [ ] All critical/blocking bugs fixed
- [ ] No known regressions
- [ ] Security: dependencies scanned (Dependabot)
- [ ] Documentation updated

### Version and changelog

- [ ] Full delta reviewed (`git log <last-tag>..stabilization/YYMM`)
- [ ] Semver determined (MAJOR / MINOR / PATCH)
- [ ] Version set in `pyproject.toml` (and any other version files)
- [ ] `CHANGELOG.md` finalized with version, date, and release number
- [ ] Migration guide written (if breaking changes)

### Release

- [ ] PR `stabilization/YYMM` -> `main` opened and CI passes
- [ ] PR merged
- [ ] Tag `vX.Y.Z` created on `main`
- [ ] CI release workflow completes successfully
- [ ] GitHub Release created with artifacts
- [ ] Artifacts verified (download and smoke test on clean environment)

### Post-release

- [ ] `stabilization/YYMM` back-merged into `development`
- [ ] `stabilization/YYMM` branch deleted
- [ ] Announce the release

---

## Changelog Format

The changelog follows [Keep a Changelog](https://keepachangelog.com/) with the
addition of the release number:

```markdown
# Changelog

## [Unreleased]

### Added
- Upcoming feature X

## [0.2.0] - 2025-07-28 (Release 2507)

### Added
- Feature A
- Feature B

### Fixed
- Bug fix C

### Changed
- Refactored D

### Removed
- Deprecated E

## [0.1.0] - 2025-05-25 (Release 2505)

### Added
- Initial release
```

---

## GitHub Release Notes Template

```markdown
## O3DE Pilot vX.Y.Z (Release YYMM)

**Highlights:**
- Feature A
- Feature B
- Important fix C

**Compatibility:**
- O3DE: 23.10+
- Python: 3.10+
- Platforms: macOS (arm64), Windows (x64), Ubuntu (x86_64), Fedora (x86_64)

**Install:**
pip install o3de-pilot==X.Y.Z

**Full Changelog:** CHANGELOG.md
**Migration Guide:** docs/migration/X.Y.Z.md (if applicable)
```

---

## FAQ

### Why not use the semver in the stabilization branch name?

Because the semver is not known when the branch is created. The team needs to
review the full set of changes *after* stabilization is complete before it can
determine whether the release is a major, minor, or patch bump. The date-based
release number (`YYMM`) is deterministic at branch-creation time.

### What if two stabilization branches are needed in the same month?

Append a sequential suffix: `stabilization/2507`, `stabilization/2507.1`.
This is rare and typically only happens for emergency patch releases.

### Can a hotfix bypass the stabilization process?

For critical security or data-loss fixes, yes. A minimal stabilization branch
can be cut, the fix applied and verified, and the branch merged to `main` the
same day. The semver bump would be PATCH.

### Who can merge into `main`?

Only release maintainers, and only from a stabilization branch PR.

### What happens to `development` during stabilization?

It stays open. Contributors continue to merge feature work into `development`
for the *next* release. The current stabilization branch only receives targeted
fixes.

---

## See Also

- [Branching Model](branching-model.md) - Branch architecture and rules
- [Contributing Guide](../CONTRIBUTING.md) - Fork workflow, PR gating, coding
  standards
