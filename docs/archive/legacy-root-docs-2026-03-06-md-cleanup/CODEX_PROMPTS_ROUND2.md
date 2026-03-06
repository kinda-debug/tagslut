# Codex Prompts — Round 2

Generated 2026-03-01. Targets: error handling, data integrity, test coverage, CLI hygiene, migration consolidation, docs freshness, type safety, provider policy.

---

## Prompt 1: Add logging to silent `except Exception` blocks

In the `tagslut/` package there are 30+ `except Exception:` blocks that silently swallow errors without logging. This is the dominant anti-pattern in the codebase.

**Files to fix** (capture the exception as `e` and add `logger.debug()` or `logger.warning()`):

- `tagslut/exec/transcoder.py` (L94, L140)
- `tagslut/exec/usb_export.py` (L92, L153)
- `tagslut/exec/engine.py` (L37)
- `tagslut/dj/classify.py` (L170)
- `tagslut/dj/export.py` (L216, L222, L229)
- `tagslut/dj/lexicon.py` (L390, L434)
- `tagslut/metadata/providers/base.py` (L200, L251)
- `tagslut/metadata/providers/deezer.py` (L41, L60, L70, L88, L95, L103)
- `tagslut/metadata/providers/traxsource.py` (L77, L107)
- `tagslut/metadata/providers/musicbrainz.py` (L79, L109, L133)
- `tagslut/storage/queries.py` (L49, L793, L805)
- `tagslut/cli/commands/dj.py` (L130, L135)
- `tagslut/core/scanner.py` (L474)

For each block: change `except Exception:` to `except Exception as e:`, add `logger.debug("...: %s", e)` at minimum (use `.warning()` for high-severity like transcoder, usb_export, storage). Ensure each module has `import logging` and `logger = logging.getLogger(...)` at the top.

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 2: Write provider IDs in recovery mode too

In `tagslut/metadata/store/db_writer.py`, the `update_database()` function only writes provider IDs (`spotify_id`, `beatport_id`, `tidal_id`, `qobuz_id`, `itunes_id`, `deezer_id`, `traxsource_id`, `musicbrainz_id`) when `mode` is `"hoarding"` or `"both"`. In recovery mode, provider IDs are discarded even though they're identity linkage fields, not hoarding-specific metadata.

**Fix**: After the `# Always write enriched_at` block (around L332-344), add a new block that always writes any non-None provider IDs regardless of mode. Keep the full hoarding metadata block as-is for the remaining fields.

Also add a test in `tests/test_enrichment_cascade.py` (or a new `tests/test_db_writer.py`) that:

1. Creates a temp SQLite DB with the files table schema
2. Calls `update_database()` in `"recovery"` mode with a result that has `beatport_id="123"` and `tidal_id="456"`
3. Asserts that both IDs are stored in the DB row

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 3: Add unit tests for `tagslut/utils/`

The `tagslut/utils/` package contains 25 modules but `tests/utils/` only contains `__init__.py`. Add test coverage for the core utility modules.

Create the following test files:

- `tests/utils/test_config.py` — test `load_config()`, missing config file handling, default values
- `tests/utils/test_file_operations.py` — test move/copy safety, path validation, audit trail generation
- `tests/utils/test_safety_gates.py` — test gate checks, duration thresholds, DJ safety rules
- `tests/utils/test_validators.py` — test path validators, format validators, checksum validators
- `tests/utils/test_db.py` — test DB connection helpers, schema version checking

Each test file should:

- Use `pytest` and `tmp_path` fixtures (no real filesystem or DB)
- Mock external I/O where needed
- Test both happy path and error cases
- Have at least 3 tests per file

Run `poetry run pytest tests/utils/ --tb=short -q` and confirm all pass, then run the full suite.

---

## Prompt 4: Retire the `scan` CLI command

The `scan` command is retired per `docs/SURFACE_POLICY.md` but is still registered in `tagslut/cli/main.py` at line 84 via `cli.add_command(scan_group, name="scan")`.

**Changes**:

1. In `tagslut/cli/main.py`: Remove the `scan_group` import and the `cli.add_command(scan_group, name="scan")` line.
2. If `tagslut/cli/scan.py` is only imported by `main.py`, add a deprecation comment at the top noting it's retained for internal use but not CLI-registered.
3. In `docs/SCRIPT_SURFACE.md`: Ensure the scan group is listed under "Retired" not "Active". Clarify that `_mgmt`, `_metadata`, `_recover` are internal hidden commands not operator-facing.
4. Add a test in `tests/test_cli_command_interface.py` that verifies `scan` is NOT in the registered CLI commands: `assert "scan" not in [cmd.name for cmd in cli.commands.values()]`

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 5: Consolidate migration system

There are 3 migration systems coexisting:

- `tagslut/migrations/` — Python with `up()`/`down()` pattern (`0002_add_dj_fields.py`) and class-based pattern (`migrate_checksum_provenance.py`)
- `tagslut/storage/migrations/` — Raw SQL files (`2026_02_03_add_duration_safety.sql`, `2026_03_01_add_dj_gig_fields.sql`)

**Consolidate** into `tagslut/storage/migrations/` with a unified runner:

1. Create `tagslut/storage/migration_runner.py` with:
   - A `migrations_applied` table: `(id INTEGER PRIMARY KEY, name TEXT UNIQUE, applied_at TEXT)`
   - A `run_pending(db_path)` function that scans `tagslut/storage/migrations/` for `.sql` and `.py` files, applies any not yet in `migrations_applied`, in filename order
   - Python migrations must export a `def up(conn):` function
   - SQL migrations are executed directly
2. Convert `tagslut/migrations/0002_add_dj_fields.py` to work with the new runner (it already has `up()`)
3. Move all migrations to `tagslut/storage/migrations/` with consistent naming: `NNNN_description.{py,sql}`
4. Add `tests/storage/test_migration_runner.py` with tests for: empty DB, idempotent re-run, Python migration, SQL migration, ordering

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 6: Update stale docs

Several docs reference retired commands or outdated patterns:

1. **`docs/PROGRESS_REPORT.md`** — Line ~48 recommends `python -m tagslut _metadata enrich`. Change to `poetry run tagslut index enrich --db <db> --hoarding --execute`. Remove any other `_metadata` references.
2. **`docs/SCRIPT_SURFACE.md`** — Line ~85-93 says "Canonical groups now call internal hidden commands (`_mgmt`, `_metadata`, `_recover`)". Rewrite to clarify these are implementation details, not operator-facing. Move `scan` from any active listing to the retired section.
3. **`docs/TROUBLESHOOTING.md`** — Line ~147 references `tagslut verify recovery` which delegates to `_recover`. If this is still the canonical invocation, leave it. If not, update the example.
4. **`tagslut/cli/commands/index.py`** — Line ~968: the hoarding example `--providers beatport,tidal,deezer` should be removed or changed to just show `tagslut index enrich --db music.db --hoarding --execute` (the default provider list is now correct).

Run `poetry run pytest --tb=short -q` and confirm all tests pass.

---

## Prompt 7: Add type annotations to `db_reader.py` and `enricher.py`

These two files have the most `# type: ignore  # TODO: mypy-strict` suppressions. Add proper type annotations.

**`tagslut/metadata/store/db_reader.py`**:

- `get_eligible_files()` — add return type `Iterator[LocalFileInfo]`, annotate all parameters
- `get_file_row()` — add return type `Optional[sqlite3.Row]`
- `get_file_info()` — add return type `Optional[LocalFileInfo]`
- `row_to_local_file_info()` — add parameter and return types
- Remove all `# type: ignore` comments where possible

**`tagslut/metadata/enricher.py`**:

- `Enricher.__init__()` — annotate all parameters
- `Enricher.__enter__()` / `__exit__()` — add proper context manager types
- `Enricher._get_provider()` — annotate return as `Optional[BaseProvider]`
- Remove all `# type: ignore` comments where possible

Run `poetry run mypy tagslut/metadata/store/db_reader.py tagslut/metadata/enricher.py --strict 2>&1 | head -30` and fix any remaining errors. Then run `poetry run pytest --tb=short -q`.

---

## Prompt 8: Add tests for `tagslut/metadata/pipeline/stages.py` and `runner.py`

The enrichment pipeline is the most critical path in the hoarding workflow but has no dedicated tests (only the newly added `test_enrichment_cascade.py` covers `apply_cascade`). Add comprehensive tests:

Create `tests/metadata/test_pipeline_stages.py`:

- Test `resolve_file()` with Beatport track ID match (Stage 0)
- Test `resolve_file()` with release ID + title matching (Stage 0b)
- Test `resolve_file()` ISRC search across multiple providers (Stage 1)
- Test `resolve_file()` text search fallback (Stage 2)
- Test `resolve_file()` title-only fallback (Stage 3)
- Test `classify_health()` — OK, truncated, extended, edge cases
- Test `normalize_title()` stripping "(Original Mix)" etc.

Create `tests/metadata/test_pipeline_runner.py`:

- Test `run_enrich_all()` with mock providers — verify stats counting
- Test `run_enrich_all()` checkpoint logging at intervals
- Test `run_enrich_all()` resumes after KeyboardInterrupt
- Test `run_enrich_file()` — not_found, not_eligible, no_match, enriched paths

Use `FakeProvider` pattern from `tests/test_enrichment_cascade.py`. Mock `db_reader` and `db_writer` with `unittest.mock.patch`.

Run `poetry run pytest tests/metadata/ --tb=short -q` then `poetry run pytest --tb=short -q` for full suite.

---

## Prompt 9: Add tests for `tagslut/exec/` modules

The execution engine (`tagslut/exec/`) handles file moves, transcoding, and USB export but has minimal direct test coverage. Add tests:

Create `tests/exec/test_engine.py`:

- Test move plan execution with mock filesystem (use `tmp_path`)
- Test quarantine plan execution
- Test error handling when source file missing
- Test receipt generation after successful move

Create `tests/exec/test_receipts.py`:

- Test receipt creation and serialization
- Test receipt verification against DB
- Test receipt dedup (same file moved twice)

Create `tests/exec/test_transcoder.py`:

- Test transcoder config parsing
- Test quality parameter mapping
- Test error handling for unsupported formats (mock ffmpeg)

Use `tmp_path` and `unittest.mock` throughout. No real filesystem operations outside tmp_path. No real ffmpeg calls.

Run `poetry run pytest tests/exec/ --tb=short -q` then `poetry run pytest --tb=short -q`.

---

## Prompt 10: Add iTunes policy block and clean up provider references

iTunes was removed from the default provider list but is still fully functional and referenced in precedence lists. Align it with the Spotify/Qobuz policy.

**Changes**:

1. In `tagslut/metadata/enricher.py` `_get_provider()`: Add a policy block for `"itunes"` matching the Spotify/Qobuz pattern: `logger.warning("iTunes provider is disabled by policy (use Apple Music via MusicBrainz).")` and `return None`.
2. In `tagslut/metadata/models/precedence.py`: Remove `"itunes"` from all precedence lists. It's already not in the default providers and the Apple Music provider (via MusicBrainz) is the replacement.
3. In `tagslut/metadata/store/db_writer.py` `_derive_library_track_key()`: Keep `itunes_id` in the fallback loop (old data may have it) but document it as legacy.
4. Keep the `itunes_id` column in `tagslut/storage/schema.py` (backward compat).
5. Keep `tagslut/metadata/providers/itunes.py` and `apple_music.py` source files but add a docstring noting they're dormant.

Run `poetry run pytest --tb=short -q` and confirm all tests pass. Verify no runtime imports of iTunes provider occur when using default providers.
