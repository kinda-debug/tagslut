# Codex Prompts — Round 3

Generated 2026-03-01. Targets: dead code removal, test coverage for critical untested modules, scanner logging, CLI refactoring, config validation, canon writeback.

---

## Prompt 1: Convert scanner `print()` to logger calls

`tagslut/core/scanner.py` (797 lines) uses raw `print()` approximately 50 times for scan summaries, per-file progress, and status output. This makes output untestable, breaks structured logging, and bleeds through when scanner is used as a library.

**Changes**:

1. Add `import logging` and `logger = logging.getLogger("tagslut.core.scanner")` at the top
2. Replace all `print(...)` calls with `logger.info(...)` or `logger.debug(...)`:
   - Summary/result lines → `logger.info()`
   - Per-file progress → `logger.debug()`
   - Error/warning messages → `logger.warning()`
3. Ensure the CLI entry points that call scanner have a StreamHandler configured so user-visible output is preserved
4. Add 2-3 tests in `tests/core/test_scanner.py` that verify log messages contain expected summary data (use `caplog` fixture)

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 2: Delete 7 dead/orphan modules

The following modules are never imported anywhere in the codebase (verified by grep across all `.py` files):

| Module | Lines |
|--------|------:|
| `tagslut/utils/plan_filter.py` | 387 |
| `tagslut/utils/artifact_manager.py` | 75 |
| `tagslut/utils/mount_tracker.py` | 81 |
| `tagslut/utils/structured_logger.py` | 66 |
| `tagslut/utils/file_filters.py` | 249 |
| `tagslut/metadata/spotify_harvest_utils.py` | 203 |
| `tagslut/metadata/spotify_partner_tokens.py` | 122 |

Total: **1,183 lines** of dead code.

**Changes**:

1. Before deleting, grep each module name AND its exported functions/classes across the entire repo to confirm zero usage
2. Delete confirmed dead modules
3. Remove any re-exports from `__init__.py` files
4. If `plan_filter.py` contains logic that belongs in `decide/planner.py`, note it in a comment in planner.py but still delete the orphan
5. Run `poetry run pytest --tb=short -q` and confirm all tests pass
6. Run `poetry run python -c "import tagslut"` to confirm no import errors

---

## Prompt 3: Add tests for `tagslut/utils/zones.py`

`ZoneManager` (473 lines) is imported by 10+ modules including `core/scanner.py`, `core/keeper_selection.py`, `storage/queries.py`, and `decide/planner.py`. It's a critical path component with zero dedicated test coverage.

Create `tests/utils/test_zones.py` covering:

- `ZoneManager` construction from a YAML config dict
- `get_zone_for_path()` with library, staging, quarantine, and unknown paths
- `zone_priority()` ordering (library > staging > quarantine)
- `coerce_zone()` with valid zone names, invalid names, and None
- `override_priorities()` if present
- `has_library_zones()` returning True/False based on config
- Edge cases: empty config, path with no matching zone, overlapping zones

Use `tmp_path` and mock config. At least 8 tests.

Run `poetry run pytest tests/utils/test_zones.py --tb=short -q` then full suite.

---

## Prompt 4: Add tests for `tagslut/dj/lexicon.py`

The DJ lexicon module (447 lines) handles scan report loading, column auto-detection, track override parsing, and enrichment cross-referencing. Zero test coverage.

Create `tests/dj/test_lexicon.py` covering:

- `_detect_columns()` with varied CSV headers (standard, reordered, missing columns)
- `load_track_overrides()` with edge cases (empty rows, comment lines, missing fields)
- `_enrich()` cross-referencing by path and artist|title
- `_normalize()` whitespace and case handling
- `load_scan_report()` with a temp CSV fixture via `tmp_path`
- Error handling: malformed CSV, missing file, empty file

At least 6 tests. Use `tmp_path` for temp CSV files.

Run `poetry run pytest tests/dj/test_lexicon.py --tb=short -q` then full suite.

---

## Prompt 5: Add tests for `tagslut/core/duration_validator.py`

Duration validation (198 lines) is a DJ safety-critical path per AGENTS.md. Zero test coverage.

Create `tests/core/test_duration_validator.py` testing:

- `check_file_duration()` with valid duration within tolerance
- Truncated file detection (measured << reference)
- Extended file detection (measured >> reference)
- Zero-length duration handling
- None duration handling
- Threshold boundary cases (at exact tolerance limits)
- Status string outputs match expected values

At least 5 tests. Mock audio file reads (no real media files).

Run `poetry run pytest tests/core/test_duration_validator.py --tb=short -q` then full suite.

---

## Prompt 6: Implement `gig status` command

`tagslut/cli/commands/gig.py` line ~92 — the `gig status` command opens a DB connection but is essentially a no-op (`pass` at line 99). It lists USB tracks by filename only with no cross-referencing.

**Implement**:

1. Query the gig set DB for expected tracks (the planned set list)
2. Scan the USB target path for actual files present
3. Diff against inventory:
   - **Current**: tracks on USB that match the set
   - **Stale**: tracks on USB that are NOT in the set (removed/replaced)
   - **Missing**: tracks in the set that are NOT on USB
4. Output a structured summary with counts and optionally per-file details with `--verbose`
5. Return exit code 0 if complete, 1 if missing tracks

Add tests in `tests/cli/test_gig_status.py` using `tmp_path` for mock USB and in-memory DB.

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 7: Add config schema validation

`tagslut/utils/config.py` — the `Config` singleton loads TOML via `get()` with dot-notation but has zero validation. Any typo in config keys silently returns `None`.

**Changes**:

1. Define a `CONFIG_SCHEMA` dict or dataclass in `tagslut/utils/config.py` that lists all known config keys with their types and default values. Derive keys from actual usage across the codebase (grep for `config.get("`)
2. Add a `validate()` method on `Config` that:
   - Warns about unknown keys (possible typos)
   - Warns about type mismatches (expected int, got string)
   - Returns a list of validation issues
3. Call `validate()` on load if `TAGSLUT_STRICT_CONFIG=1` env var is set (opt-in to avoid breaking existing workflows)
4. Add tests in `tests/utils/test_config.py` (extend existing) for: valid config passes, unknown key warns, type mismatch warns, missing required key warns

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 8: Refactor `execute move-plan` from script wrapper to native

`tagslut/cli/commands/execute.py` — all three subcommands (`move-plan`, `quarantine-plan`, `promote-tags`) delegate to `run_python_script("tools/review/...")` with raw unparsed args. No Click validation, no shared DB management, hard to test.

**Refactor `execute move-plan`**:

1. Add proper Click options: `--plan` (CSV path, required), `--db` (DB path), `--dry-run` (flag), `--verify` (flag)
2. Call `tagslut.exec.engine` directly instead of shelling out to `tools/review/move_from_plan.py`
3. Read the plan CSV, validate rows, execute moves via `engine.execute_move_plan()`, write receipts
4. If `--verify` is set, run `tagslut.verify` parity checks after moves
5. Keep the old `tools/review/move_from_plan.py` script working but mark it as deprecated
6. Add an integration test in `tests/exec/test_engine.py` that tests the full flow with `tmp_path`

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 9: Add canon file writeback function

`tagslut/metadata/canon/apply.py` — `apply_canon()` transforms a tag dictionary in memory (196 lines, well implemented) but there is **no reusable FLAC/MP3 writeback function**. The `canonize` CLI command in `misc.py` does inline writeback with duplicated mutagen logic.

**Add**:

1. `write_canon_to_file(path: Path, rules: CanonRules, *, dry_run: bool = True) -> dict` in `tagslut/metadata/canon/apply.py`:
   - Read tags from FLAC/MP3 via mutagen
   - Apply `apply_canon()` to get the transformed tag dict
   - If not dry_run, write the transformed tags back to the file
   - Return a diff dict showing `{field: (old_value, new_value)}` for changed fields
2. Refactor the `canonize` CLI command in `tagslut/cli/commands/misc.py` to use `write_canon_to_file()` instead of inline mutagen logic
3. Add tests in `tests/test_canon_apply.py` (extend existing):
   - Test `write_canon_to_file()` in dry_run mode returns diff without modifying file
   - Test with a mock mutagen file object
   - Test with unsupported file format raises appropriate error

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 10: Fix `_row_to_audiofile` exception handling and add dead module marker

`tagslut/storage/queries.py` lines ~787-808 — two `except Exception` blocks in `_row_to_audiofile()` catch ANY error when reading row fields, but the `if "key" in row.keys()` guards already prevent `KeyError`. The broad catches mask real bugs.

Also: `tagslut/metadata/beatport_import_my_tracks.py` (392 lines) is never imported anywhere — it's dead code.

**Changes**:

1. In `_row_to_audiofile()`: Remove the two broad `try/except Exception` blocks. The existing `if "key" in row.keys()` guards are sufficient. If a guard is missing for any field, add one instead of wrapping in try/except.
2. Move `tagslut/metadata/beatport_import_my_tracks.py` to `tools/beatport_import_my_tracks.py` (it's a standalone script, not a library module). Remove from `tagslut/metadata/`.
3. Add a test for `_row_to_audiofile()` with a mock row dict that has all expected columns, and one with missing columns.

Run `poetry run pytest --tb=short -q` and confirm all tests pass.
