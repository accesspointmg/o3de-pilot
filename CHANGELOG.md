# Changelog

All notable changes to o3de-pilot are documented in this file.

## v0.1.0 — 2025-05-25

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
