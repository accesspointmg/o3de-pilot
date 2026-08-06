# Changelog

All notable changes to o3de-pilot are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Each release also carries a **release number** derived from the date the
stabilization branch was cut (`YYMM`). See
[docs/release-process.md](docs/release-process.md) for details.

## [Unreleased]

Changes on `development` that have not yet been included in a release.

## [0.1.0] - 2025-05-25 (Release 2505)

### Bug Fixes

| # | Severity | Location | Issue | Resolution |
|---|----------|----------|-------|------------|
| 1 | **High** | `commands/layout.py` | Layout constructor mismatch | Fixed — layout merged into workspace |
| 2 | **Medium** | `commands/gem.py`, `project.py`, etc. | Pydantic v1 `.dict()` calls | Fixed — manual dict building now |
| 3 | **Medium** | `commands/manifest.py` `remove_command` | Path comparison mismatch on Windows | Fixed — uses `.resolve().as_posix()` for cross-platform comparison |
| 4 | **Low** | `test_resolver.py` | Vacuously true assertion | Fixed — changed `>= 0` to `> 0` |
| 5 | **Medium** | `core/manifest.py` | Legacy duplicate module | Fixed — removed entirely |
| 6 | **Low** | `ai/provider.py` | Outdated model strings | Fixed — updated to current models |

### Implementation Phases Completed

**Phase 0: Bug Fixes & Hygiene**

1. Fix `.dict()` → `.model_dump()` in `commands/gem.py`, `project.py`, `engine.py`, `template.py`
2. Fix `Layout` constructor mismatch in `commands/layout.py` `update_command`
3. Fix path comparison in `commands/manifest.py` `remove_command`
4. Fix vacuously true assertion in `test_resolver.py`
5. Deprecate `core/manifest.py` — redirect callers to `resolver`
6. Update AI provider model strings in `ai/provider.py`

**Phase 1: Model Alignment**

7. `Dependencies` model supports all 7 object types (projects, templates, overlays, repos, restricteds)
8. `Download` model has `source_sha256`, `lfs_sha256`; `Binary` has `sha256`
9. `deprecated: Optional[str]` on all object models
10. `hooks: Optional[dict]` on engine/gem/project/template/overlay models
11. `optional_dependent`, `peer_dependent` on engine/gem/project/template/overlay models
12. `Release.version` → `Release.name` (with alias)
13. `upgrade.py` converters handle new fields during 1→2 upgrade
14. `test_models.py` and `test_upgrade.py` updated for new fields

**Phase 2: Lock File & Conflict Detection**

15. `Resolver` builds full transitive dependency DAG
16. Version conflict detection with clear error reporting
17. `resolved_o3de_manifest.json` includes pinned transitive dependency versions (lock file)
18. `--dry-run` flag infrastructure shared across commands
19. Extensive tests — conflict scenarios, diamond dependencies, version range overlaps

**Phase 3: Integrity & Auto-Install**

20. SHA-256 verification end-to-end (`RemoteObject.source_sha256` → `download_sync(expected_sha256=)`)
21. Auto-resolve: `resolver.auto_install_missing()` + `manifest resolve --install [--yes]`
22. `--dry-run` on `registry install` and `resolve` commands
23. Deprecation warnings wired into resolution

**Phase 4: Stub Command Implementation**

24. `gem create` — scaffold gem directory from template, register it
25. `gem info` — display full object metadata from resolved manifest
26. `gem search` — search across registered remotes
27. `project init` — scaffold project from template, register it
28. `project build` — invoke CMake with proper preset
29. `project run` — launch built executable
30. `project add` — add gem dependency to project
31. `engine register` / `engine unregister` — add/remove engine paths
32. `template info` — display template metadata
33. `registry uninstall` — remove cached/installed remote objects
34. `registry update` — refresh + re-resolve with latest versions

**Phase 5: Publish, Optional Deps, Deprecation**

35. `publish` command — JSON Schema validation against canonical 2.0.0 schemas via `core/schema.py`
36. Optional/peer dependency resolution — surfaced in `manifest resolve` output with suggestions
37. `audit` command — scan for deprecated objects, missing integrity, unresolvable optional deps

**Phase 6: Hooks & Workspace**

38. Hooks execution engine — pre/post install scripts with confirmation, timeout, filtering
39. `workspace` command — multi-project coordination with shared engines/gems
40. `deps tree` command — Rich-formatted dependency graph visualization

**Phase 7: Test Coverage & Polish**

41. Deep behavioral integration tests for commands (replacing shallow invocation checks)
42. Tests for `git_utils.py`, `config.py`
43. Removed deprecated `core/manifest.py`
44. GUI: deprecation badges, integrity status, dependency tree view

### Test Coverage Campaign (E0–E5)

Starting from 29% overall (48% CLI+core excl. GUI) with 429 tests (~40 shallow smoke checks):

- **E0:** Created `tests/conftest.py` with shared fixtures (`runner`, `temp_manifest`, `mock_manifest`, `mock_store`, `make_gem()`, etc.)
- **E1:** Rewrote 40 shallow tests into isolated behavioral tests with precise assertions
- **E2:** Extended core library coverage — `store.py` (41→85%), `upgrade.py` (68→85%), `resolver.py` (73→85%), `git_utils.py` (49→80%), `workspace.py` (44→80%)
- **E3:** Command coverage — added tests for engine, gem, project, registry, register, workspace, deps, template, overlay, repo, audit, manifest, config, publish
- **E4:** AI module coverage — `provider.py` (0→70%), `command_router.py` (0→90%)
- **E5:** Mop-up — `schema.py` (79→95%), `hooks.py` (73→90%), `network.py` (74→90%), `paths.py` (81→95%), `models.py` (88→95%)

**Final result:** 770 tests passing, 47.3% overall / 74.5% CLI+core coverage (31 test files, ~8.8k test lines).

### PR Triage & Dependency Maintenance (F1–F4)

11 open PRs triaged and resolved (10 Dependabot, 1 external contributor). 0 remaining.

**GitHub Actions — merged (#22, #23, #25, #26, #27):**
- `actions/download-artifact` v7 → v8
- `actions/upload-artifact` v6 → v7
- `nick-fields/retry` v3 → v4
- `dependabot/fetch-metadata` v2 → v3
- `softprops/action-gh-release` v2 → v3

**Python dependencies — batched conservative bumps:**
- `click` >=8.0 → >=8.1 (bug fixes only)
- `ruff` >=0.1 → >=0.4 (dev-only linter)
- `setuptools` >=61.0 → >=70.0 (no pkg_resources usage found)
- `Pillow>=10.0` added to `[dev]` extras for `scripts/generate_icons.py`
- Closed Dependabot PRs #28, #29, #31 (batched), #24 (Pillow moved to [dev])

**Deferred:**
- `PySide6` stays at >=6.5 — large jump, may break on older Python (PR #32 closed)

### GUI Test Harness & AI Maturity (G1–G4)

**G1. GUI Test Harness:**
- Added `pytest-qt>=4.2` to `[dev]` extras
- Created `tests/test_gui.py` — 10 smoke tests (MainWindow, SplashScreen, ObjectCatalogScreen, ObjectInspector, SettingsDialog)
- Uses demo data and `qtbot` fixture; no network or AI key required

**G2. OpenAI v2 Migration:**
- Audited `ai/provider.py` — already uses modern `OpenAI()` client and `client.chat.completions.create()` (v2-compatible)
- Bumped `openai>=1.0` → `openai>=2.0` in pyproject.toml
- All 58 AI tests pass with openai 2.38.0

**G3. Coverage Gate:**
- Added `[tool.coverage.run]` with `omit = ["o3de_pilot/gui/*"]`
- Added `[tool.coverage.report]` with `fail_under = 74` (ratchet up as coverage grows)
- CLI+core at 74.4% — gate passes, prevents regression

**G4. AI Command Maturity:**
- Replaced 4 stub commands with real AI-powered implementations:
  - `diagnose` reads build logs (CMakeOutput/Error.log) and sends to AI for analysis
  - `generate` sends structured prompt for gem/component/script generation
  - `migrate` gathers project.json/gem.json/CMakeLists.txt and asks AI for migration plan
  - `explain` sends topic to AI with O3DE context
- Updated tests from stub assertions to provider-mocked integration tests (12 tests)

**Final result:** 782 tests passing, 32 test files, 74.4% CLI+core coverage with regression gate.

### Future Work Round 2 (H1–H4)

**H1. Deeper GUI Test Coverage:**
- Expanded `test_gui.py` from 10 smoke tests to 32 interaction tests (~290 lines)
- Added 5 new test classes: TestCatalogInteraction (6), TestMainWindowTabs (5), TestProxyModelFiltering (8), TestObjectModel (3), TestSettingsDialog (1)
- Fixed ObjectListView bug: `select_object()` / `scroll_to_object()` called `self._model.get_name(index)` on proxy model — changed to `index.data(ObjectRole.Name)` with local import

**H2. Coverage Ratchet to 80%:**
- Created `test_coverage_h2.py` (~680 lines, 60 new tests)
- Coverage areas: audit edge cases, project build/run, deps JSON/tree, workspace update/solve, registry install/list, publish validate/push, gem search, repo/overlay edge cases
- Key fix: patching at import-site (`o3de_pilot.core.paths.get_manifest_path`) not module-level
- Coverage gate bumped: `fail_under = 74` → `fail_under = 80` (80.05% actual)

**H3. AI Streaming:**
- Replaced stub `stream()` methods with real token-by-token streaming in all providers:
  - OpenAIProvider: `client.chat.completions.create(stream=True)` with `chunk.choices[0].delta.content`
  - ClaudeProvider: `client.messages.stream()` context manager with `text_stream` iterator
  - GeminiProvider: httpx SSE streaming to `streamGenerateContent?alt=sse` endpoint, line-delimited JSON
- GUI integration: `AIWorker.token` signal → `AITab._on_ai_token()` → progressive bubble rendering with auto-scroll
- Added 4 streaming unit tests (OpenAI, Claude, Gemini, NoAI fallback)

**H4. PySide6 Version Bump:**
- Bumped floor from `PySide6>=6.5` → `PySide6>=6.7` (Qt 6.7 LTS, Python 3.12 support)
- Fixed `QSortFilterProxyModel.invalidateFilter()` deprecation (deprecated in Qt 6.10+)
  - Added `_QT_HAS_FILTER_CHANGE` flag + `_refilter()` helper using `beginFilterChange()`/`endFilterChange()` on Qt 6.9+
  - Falls back to `invalidateFilter()` on older Qt versions
- All tests pass with `-W error::DeprecationWarning` — zero deprecation warnings

**Final result:** 868 tests passing, 35 test files (~11.6k lines), 80.05% CLI+core coverage, PySide6>=6.7 with Qt deprecation-clean.

### I. Workspace Schema & GUI Tab — 2026-05-25

**I1–I6: Canonical workspace JSON Schema, Pydantic model, file-ownership tracking, and Workspaces GUI tab.**

- Created `canonical.o3de.org/src/o3de-workspace-2.0.0.json` — Draft 7, fields: workspace header, created, root_object/root_type, sources[], overlays[], file_owners{}
- Added `WorkspaceHeader` + `WorkspaceMeta(BaseO3DEObject)` Pydantic models in `core/models.py`
- Added `WORKSPACE_SCHEMA_FILENAME` in `core/schema.py` (separate constant — workspace is not an ObjectType)
- Migrated `commands/workspace.py` from `.workspace.json` (hidden) to `workspace.json` (visible), with legacy fallback
- All write paths use Pydantic validation via `_build_workspace_meta()` + `_write_workspace_meta()`
- Added `file_owners: dict[str, str]` to `Workspace` class — `_link_object_files()` records ownership, `_apply_overlay()` transfers it
- New `gui/workspace_tab.py` — `WorkspaceTab(QWidget)` with QSplitter, color-coded directory tree, HSL color legend, async QThread tree loading, demo mode
- Wired tab into `main_window.py` as fourth tab ("Workspaces"); demo mode swaps in synthetic data
- 23 new tests in `test_workspace_i.py`: schema validation, model round-trip, migration fallback, file ownership, GUI tab

**Final result:** 891 tests passing, 36 test files (~12k lines), 80.30% CLI+core coverage.
