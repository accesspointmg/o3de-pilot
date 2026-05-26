# o3de-pilot: Current State

**As of 2025-05-25 — 55 source files (~21.5k lines), 31 test files (~8.8k lines), 770 tests passing.**

47.3% overall coverage / 74.5% CLI+core coverage (GUI excluded).

---

## Module Reference

| Module | Lines | Tests | Description |
|--------|-------|-------|-------------|
| `core/upgrade.py` | 1264 | 66 | Most complete module — full 0→1→2 schema chain |
| `core/resolver.py` | 1610 | ~50 | Resolution, parent-child chains, overlays, DAG, conflict detection, lock file |
| `core/store.py` | 924 | ~30 | Remote fetch, SHA-256 cache keys, git clone + zip download |
| `core/solver.py` | 422 | ~25 | resolvelib-based dependency solver |
| `core/workspace.py` | 336 | ~15 | Symlink-based build dirs with overlay support (replaces old layout.py) |
| `core/paths.py` | 266 | ~20 | User dirs, manifest paths, versioned filenames |
| `core/models.py` | 493 | ~30 | Pydantic v2 models for all 7 object types, full 2.0.0 alignment |
| `core/hooks.py` | 179 | ~10 | Pre/post install hook execution with confirmation/timeout |
| `core/network.py` | 214 | ~8 | Connectivity singleton, monitoring, listeners |
| `core/git_utils.py` | 390 | ~10 | GitHub + GitLab releases, URL parsing |
| `core/config.py` | 93 | ~8 | YAML config with dot-notation |
| Commands (17 files) | ~4018 | — | All command groups implemented |
| GUI (19 files) | ~9267 | — | Full PySide6 catalog UI with async icons, filters, inspector, AI tab, workspace solver |

### Working Commands

- `manifest resolve/show/upgrade/add/remove/set/get`
- `registry search/install/refresh/add-remote/remove-remote/list-remotes/uninstall/update`
- `workspace create/update/list/show/delete/tree`
- `config get/set/unset/list/path`
- `register add/remove/all/status`
- `gem list/create/info/search`
- `project list/init/build/run/add`
- `engine list/register/unregister`
- `template list/info`
- `deps tree/list/why`
- `publish validate/push`
- `audit` (deprecated objects, integrity, conflicts)
- `gui`
- `ai ask`

---

## Feature Completeness

All planned spec features are implemented:

| Priority | Feature | Implementation |
|----------|---------|----------------|
| **P0** | Lock file with pinned transitive deps | Resolver builds DAG, pins in `resolved_o3de_manifest.json` |
| **P0** | Conflict detection | `_detect_conflicts` in resolver |
| **P1** | Integrity checksums | `RemoteObject.source_sha256` → `download_sync(expected_sha256=)` |
| **P1** | Auto-resolve dependencies | `resolver.auto_install_missing()` + `manifest resolve --install [--yes]` |
| **P1** | Dry-run mode | Supported on resolve/install commands |
| **P2** | Publish with schema validation | Validates against canonical 2.0.0 JSON Schemas via `core/schema.py` |
| **P2** | Optional/peer dependency handling | Surfaced in `manifest resolve` output with suggestions |
| **P2** | Deprecation/advisory system | `_check_deprecations` in resolver, badges in GUI |
| **P3** | Hooks execution | `core/hooks.py` with confirmation, timeout, filtering |
| **P3** | Workspace coordination | `commands/workspace.py` + `core/workspace.py` |

### Stub Commands — All Replaced

All previously-stubbed commands have real implementations. AI commands (`diagnose`, `generate`, `migrate`, `explain`) are still basic but functional.

### Model Alignment — Complete

`Dependencies` supports 7 types, `Download` has SHA fields, `deprecated`/`hooks`/`optional_dependent`/`peer_dependent` on all object models, `Release` uses `name`.

### Known Gaps

- ❌ No GUI tests (needs pytest-qt / QTest harness — separate initiative)
- AI commands are basic but functional

---

## Test Coverage

**770 tests across 31 test files (~8.8k lines). 47.3% overall / 74.5% CLI+core (GUI excluded).**

### Coverage by Module

| Module | Coverage | Notes |
|--------|----------|-------|
| `core/models.py` | ~95% | Remaining: edge-case validators |
| `core/paths.py` | ~95% | Platform paths, missing home |
| `core/schema.py` | ~95% | Missing schema dir, import error |
| `core/hooks.py` | ~90% | Timeout, permission denied, filtering |
| `core/network.py` | ~90% | Listener callbacks, concurrent |
| `core/upgrade.py` | ~85% | Remote fetching, overlay upgrade, directory walk |
| `core/resolver.py` | ~85% | Sanitize, overlays, layout objects, change detection |
| `core/store.py` | ~85% | Fetch, refresh, download, search |
| `core/git_utils.py` | ~80% | Default branch, upstream, releases |
| `core/workspace.py` | ~80% | Link objects, create link, create workspace |
| `ai/command_router.py` | ~90% | Regex matrix, precedence, classification |
| `ai/provider.py` | ~70% | Factory routing, stream, ImportError |
| `commands/publish.py` | ~90% | Push success, dry-run |
| `commands/config.py` | ~85% | Get/set/unset round-trip |
| `commands/deps.py` | ~80% | List, why, build_tree recursion |
| `commands/audit.py` | ~80% | Deprecated, integrity, conflicts |
| `commands/manifest.py` | ~80% | Show, set/get, upgrade, resolve --install |
| `commands/register.py` | ~75% | resolve_to_json, CLI flows |
| `commands/gem.py` | ~75% | Info, search, register, unregister |
| `commands/engine.py` | ~75% | Create, register, unregister |
| `commands/template.py` | ~70% | Info, create, instance, register |
| `commands/overlay.py` | ~70% | List, create, register, unregister |
| `commands/repo.py` | ~70% | List, create, register, unregister |
| `commands/project.py` | ~70% | Init, register, build, run, add |
| `commands/registry.py` | ~70% | Search, install, uninstall, refresh |
| `commands/workspace.py` | ~65% | Create, update, show, delete, tree, solve |
| GUI (`gui/*.py`) | 0% | 4855 stmts — deferred (needs pytest-qt) |

### Test Infrastructure

- **Shared `conftest.py`** with fixtures: `runner` (CliRunner), `temp_manifest`, `temp_gem`, `temp_project`, `temp_engine`, `temp_template`, `mock_manifest`, `mock_store`, `resolved_manifest_factory`, `make_gem()`
- **Mock at import site** (`o3de_pilot.commands.X.func`) not source module
- **Per-module test files** for commands at this scale
- **AI tests** mock SDK imports — no API keys required

### Verification

```bash
python -m pytest src/cli/tests/ --cov=o3de_pilot --cov-report=term-missing -q
```

Future gate: `--cov-fail-under=80` in `pyproject.toml` (excluding `gui/`).

---

## Design Decisions

- **Deprecate `core/manifest.py`** rather than refactoring it — `resolver.py` already supersedes it completely
- **Lock file format:** extend existing `resolved_o3de_manifest.json` rather than introducing a new file — matches the spec's intent
- **Auto-install default:** require explicit `--yes` flag for auto-fetching dependencies (safe default, per npm/cargo convention)
- **Hooks sandboxing:** hooks require user confirmation before execution (security)
- **Shared `conftest.py`** over per-file fixture duplication
- **Mock at import site** (`o3de_pilot.commands.X.func`) not source module
- **Test file organization:** per-module test files for commands at this scale
- **AI tests** mock SDK imports — no API keys required
