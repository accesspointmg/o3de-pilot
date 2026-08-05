# Branching Model

O3DE Pilot follows the branching model used across the
[Open 3D Engine](https://o3de.org) family of repositories.

## Branch Architecture

```
main (protected)
 |
 |<--- merge from stabilization/YYMM (only way changes land on main)
 |
 |-- tag: v0.1.0  (release 2505)
 |-- tag: v0.2.0  (release 2507)
 |-- tag: v1.0.0  (release 2510)
 |
development (protected, branched from main)
 |
 |<--- PRs from contributor forks (automated + human review)
 |
 |-- stabilization/2507 (branched from development when release window opens)
 |     |
 |     |-- targeted fix commits
 |     |-- version set after semver determination
 |     |
 |     '--- merge into main -> tag vX.Y.Z -> build & package
 |
 '-- stabilization/2510
       '-- ...
```

## Branches

### `main`

The release branch. Protected. Contains only release-quality code.

- **Receives merges from:** `stabilization/*` branches only.
- **Never receives:** direct pushes or PRs from contributors.
- **Tags:** Every merge from a stabilization branch is tagged with the semver
  (e.g., `v0.1.0`). Release artifacts are built from these tags.

### `development`

The integration branch. Protected. This is where all day-to-day work lands.

- **Receives merges from:** Pull requests opened by contributors from their
  forks.
- **Branches into:** `stabilization/YYMM` when the team decides to cut a
  release.

### `stabilization/YYMM`

A time-boxed branch created from `development` when the team decides enough
work has accumulated to justify a release. The `YYMM` suffix is the release
number, derived from the year and month the branch is cut (e.g., `2507` for
July 2025).

- **Receives:** Only targeted bug fixes and documentation updates. No new
  features.
- **Merges into:** `main` when stabilization is complete.
- **Back-merged into:** `development` after the release so that fixes are not
  lost.
- **Deleted:** After the back-merge is complete.

The semver (MAJOR.MINOR.PATCH) is **not known** when the stabilization branch
is created. It is determined at the end of stabilization by reviewing the full
delta since the last release. This is why the branch uses the date-based
release number instead of the version.

### Feature branches (on forks)

Contributors fork the repository, set the upstream remote, and create feature
branches from `development`. These branches are not protected and are not
pushed to the upstream repository.

## Branch Protection Rules

### `main`

| Rule | Setting |
|---|---|
| Require pull request before merging | Yes |
| Restrict who can push | Release maintainers only |
| Require status checks to pass | Yes (all CI checks) |
| Require linear history | Yes |
| Allow bypassing | No |

### `development`

| Rule | Setting |
|---|---|
| Require pull request before merging | Yes |
| Require status checks | `dco-check`, `lint`, `test` |
| Require approving reviews | 1+ from CODEOWNERS |
| Dismiss stale reviews on new pushes | Yes |
| Require conversation resolution | Yes |

## Contributor Workflow

```bash
# 1. Fork o3de-pilot on GitHub

# 2. Clone your fork
git clone https://github.com/<you>/o3de-pilot.git
cd o3de-pilot

# 3. Set the upstream remote
git remote add upstream https://github.com/accesspointmg/o3de-pilot.git
git fetch upstream

# 4. Create a feature branch from development
git checkout -b feature/my-feature upstream/development

# 5. Do your work. Sign off every commit (DCO).
git commit -s -m "feat(resolver): add diamond-dependency detection"

# 6. Keep your branch up to date
git fetch upstream
git rebase upstream/development

# 7. Push to your fork
git push origin feature/my-feature

# 8. Open a PR on the upstream repo targeting 'development'
```

## Visual Timeline

```
development:  --*--*--*--*--*--*--------------*--*--*--*-- (continues)
                            |                  ^
                            v                  | back-merge
              stabilization/2507:  --*--*--fix-|
                                    review     |
                                    decide: v0.1.0
                                    set version|
                                               v
main:         ---------------------------------*-- (tag: v0.1.0, build & publish)
```

## See Also

- [Release Process](release-process.md) - Full release lifecycle
- [Contributing Guide](../CONTRIBUTING.md) - PR workflow and coding standards
