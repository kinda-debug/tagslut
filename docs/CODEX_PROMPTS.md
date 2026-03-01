# Codex Implementation Prompts

Generated 2026-03-01 from a full repo audit. Each prompt is self-contained and
can be submitted to Codex independently. Work them in order — later prompts may
depend on earlier ones.

---

## Prompt 0 — Close Stale Issues (Manual / GitHub CLI)

> Not a Codex task — do this by hand or with `gh`.

These 5 issues are all resolved on disk but still open on GitHub:

| Issue | Why it's resolved |
|---|---|
| #93 | Smoke tests exist: `tests/filters/test_filters_smoke.py`, `tests/core/test_metadata_smoke.py`, `tests/core/test_policy_smoke.py`, `tests/recovery/test_recovery_smoke.py`, `tests/storage/test_migrations_smoke.py` |
| #94 | `tagslut_import/` no longer exists |
| #95 | All AGENTS.md-referenced docs exist: `REPORT.md`, `docs/REDESIGN_TRACKER.md`, `docs/PHASE5_LEGACY_DECOMMISSION.md`, `docs/SCRIPT_SURFACE.md`, `docs/SURFACE_POLICY.md` |
| #96 | `tagslut/legacy/` no longer exists. Only root `legacy/` remains. |
| #97 | `tagslut/integrity_scanner.py` no longer exists |

Close each with:
```bash
gh issue close 93 --comment "Resolved: smoke tests exist for all 5 submodules."
gh issue close 94 --comment "Resolved: tagslut_import/ directory no longer exists."
gh issue close 95 --comment "Resolved: all referenced docs exist on disk."
gh issue close 96 --comment "Resolved: tagslut/legacy/ no longer exists; consolidated to root legacy/."
gh issue close 97 --comment "Resolved: tagslut/integrity_scanner.py no longer exists."
```

---

## Prompt 1 — Inline `_mgmt` shim into canonical commands

**Priority: HIGH**
**Branch: `refactor/inline-mgmt-shim`**
**Estimated scope: ~1200 LOC moved, 5 files changed**

```
TASK: Eliminate the _mgmt hidden CLI group by inlining its logic into the
canonical command modules that delegate to it via run_tagslut_wrapper.

CONTEXT:
- tagslut/cli/commands/_mgmt.py (1199 LOC) is a hidden Click group registered
  as `_mgmt` on the root CLI. It contains the REAL implementations of:
    - `register` (inventory registration) — used by `index register`
    - `check` (duplicate pre-check) — used by `index check`
    - `check-duration` — used by `index duration-check`
    - `audit-duration` — used by `index duration-audit`, `verify duration`,
      `report duration`
    - `set-duration-ref` — used by `index set-duration-ref`
    - M3U generation (default invocation with --m3u) — used by `report m3u`

- The canonical commands in index.py, verify.py, report.py currently delegate
  via `run_tagslut_wrapper(["_mgmt", "subcommand", *args])`, which spawns a
  subprocess (`python -m tagslut _mgmt ...`). This is slow and breaks
  debuggability.

- tagslut/cli/runtime.py defines `run_tagslut_wrapper()` which calls
  `run_subprocess([sys.executable, "-m", "tagslut", *args])`.

WHAT TO DO:
1. Read tagslut/cli/commands/_mgmt.py in full. Understand every subcommand and
   the helper functions they use (lines 16-212 are helpers, 213+ are commands).

2. For each canonical command that delegates to _mgmt:
   a) Move the Click command implementation from _mgmt.py into the canonical
      module (index.py, verify.py, or report.py).
   b) Move only the helper functions that command needs. If a helper is shared
      by multiple commands, put it in a new file:
      tagslut/cli/commands/_index_helpers.py
   c) Replace the run_tagslut_wrapper shim with the direct implementation.
   d) Preserve ALL Click options, arguments, and help text exactly.

3. Specific mapping:
   - _mgmt `register` → index.py `index_register` (replace the wrapper)
   - _mgmt `check` → index.py `index_check` (replace the wrapper)
   - _mgmt `check-duration` → index.py `index_duration_check` (replace wrapper)
   - _mgmt `audit-duration`:
     * Used by index.py `index_duration_audit` — inline there
     * Used by verify.py `verify duration` — call the same function
     * Used by report.py `report duration` — call the same function
     * → Extract to _index_helpers.py as a shared callable, wire from all 3
   - _mgmt `set-duration-ref` → index.py `index_set_duration_ref` (replace wrapper)
   - _mgmt M3U mode (mgmt() default with --m3u) → report.py `report_m3u` (replace wrapper)

4. After all moves:
   - _mgmt.py should be EMPTY or contain only the group registration with a
     deprecation warning for any direct `tagslut _mgmt` invocations.
   - Delete _mgmt.py entirely if no backward compat is needed (it's hidden).
   - Remove `from tagslut.cli.commands._mgmt import register_mgmt_group` from
     main.py and the `register_mgmt_group(cli)` call — BUT ONLY if you remove
     the group entirely. If keeping a deprecation stub, leave it.

5. Update imports. Remove unused `run_tagslut_wrapper` and `WRAPPER_CONTEXT`
   imports from files that no longer need them.

CONSTRAINTS:
- Do NOT change any business logic. This is purely a structural move.
- Do NOT change command names, options, or help text.
- Do NOT touch _metadata.py in this PR (that's a separate task).
- Run `poetry run pytest -x` and confirm 274 tests pass.
- Run `poetry run flake8 tagslut/cli/` and ensure no new violations.

ACCEPTANCE CRITERIA:
- `tagslut index register --help` works without spawning a subprocess
- `tagslut index check --help` works without spawning a subprocess
- `tagslut report m3u --help` works without spawning a subprocess
- `tagslut report duration --help` works without spawning a subprocess
- `tagslut verify duration --help` works without spawning a subprocess
- No test calls `run_tagslut_wrapper(["_mgmt", ...])`
- 274 tests pass
- _mgmt.py is deleted or reduced to a deprecation stub < 20 LOC
```

---

## Prompt 2 — Inline `_metadata` shim into canonical commands

**Priority: HIGH**
**Branch: `refactor/inline-metadata-shim`**
**Depends on: Prompt 1 (so patterns are established)**

```
TASK: Eliminate the _metadata hidden CLI group by inlining its logic into the
canonical command modules that delegate to it via run_tagslut_wrapper.

CONTEXT:
- tagslut/cli/commands/_metadata.py (660 LOC) is a hidden Click group with:
    - `enrich` (batch metadata enrichment) — used by `index enrich`
    - `auth-status` — used by `auth status`
    - `auth-init` — used by `auth init`
    - `auth-refresh` — used by `auth refresh`
    - `auth-login` — used by `auth login`

- Helper functions (lines 16-180):
    - _local_file_info_from_path() — builds LocalFileInfo from a file path
    - _print_enrichment_result() — pretty-prints enrichment results
    - _tidal_device_login() — interactive Tidal OAuth device flow
    - _qobuz_login() — interactive Qobuz email/password login
    - _beatport_token_input() — manual Beatport token paste

- These helpers are also imported by misc.py (the `enrich-file` standalone
  command). So they must remain importable.

WHAT TO DO:
1. Read _metadata.py in full. Map every subcommand and helper.

2. Move `enrich` command implementation → index.py as `index_enrich`
   (replacing the current run_tagslut_wrapper shim).

3. Move auth commands (auth-status, auth-init, auth-refresh, auth-login)
   → auth.py, replacing all 4 wrapper shims.

4. Move helper functions to tagslut/cli/commands/_auth_helpers.py so they
   remain importable by misc.py:
   - _tidal_device_login
   - _qobuz_login
   - _beatport_token_input

   Move enrichment helpers to tagslut/cli/commands/_enrich_helpers.py:
   - _local_file_info_from_path
   - _print_enrichment_result

5. Update misc.py imports to point to the new helper locations.

6. Delete _metadata.py or reduce to a deprecation stub.

7. Remove register_metadata_group from main.py if the group is deleted.

CONSTRAINTS:
- Do NOT change business logic, only move code.
- Do NOT touch _mgmt.py (should be done in prior PR).
- Preserve all Click option names and help text exactly.
- Run `poetry run pytest -x` — 274 tests must pass.

ACCEPTANCE CRITERIA:
- `tagslut auth status --help` works without spawning a subprocess
- `tagslut auth login tidal` works without spawning a subprocess
- `tagslut index enrich --help` works without spawning a subprocess
- _metadata.py is deleted or reduced to a deprecation stub < 20 LOC
- misc.py `enrich-file` command still works (uses moved helpers)
- 274 tests pass
```

---

## Prompt 3 — Clean up `pyproject.toml` redundant dependency

**Priority: LOW**
**Branch: `chore/pyproject-cleanup`**

```
TASK: Remove the redundant pyrekordbox entry from [tool.poetry.dependencies]
in pyproject.toml.

CONTEXT:
- pyproject.toml declares dependencies in [project] (PEP 621, the canonical
  source) and [tool.poetry.dependencies].
- [tool.poetry.dependencies] now only has `python` and `pyrekordbox`. The
  python constraint must stay (Poetry needs it). The pyrekordbox line is
  redundant — it's already in [project].dependencies.

WHAT TO DO:
1. Remove the `pyrekordbox = ">=0.3,<1.0"` line from [tool.poetry.dependencies].
2. Keep `python = ">=3.11,<4.0"` in [tool.poetry.dependencies].
3. Run `poetry check` — must pass.
4. Run `poetry lock --no-update` — lock file must regenerate cleanly.
5. Run `poetry install` — must succeed.
6. Run `poetry run pytest -x` — 274 tests must pass.

The resulting [tool.poetry.dependencies] section should be:
```toml
[tool.poetry.dependencies]
python = ">=3.11,<4.0"
```

ACCEPTANCE CRITERIA:
- `poetry check` passes
- `poetry install` succeeds
- `poetry run pytest` passes
- pyrekordbox only appears once in pyproject.toml (in [project])
```

---

## Prompt 4 — Implement `tagslut scan` with real orchestrator backend

**Priority: MEDIUM**
**Branch: `feat/scan-orchestrator`**

```
TASK: Replace the placeholder stubs in tagslut/cli/scan.py with real
implementations backed by the existing tagslut/scan/ orchestrator module.

CONTEXT:
- tagslut/cli/scan.py has 5 subcommands (enqueue, run, status, issues, report)
  that are ALL placeholder stubs returning hardcoded data.
- tagslut/scan/ is a full module with real implementations:
    - orchestrator.py — the scan orchestration engine
    - discovery.py — file discovery
    - classify.py — file classification
    - validate.py — validation rules
    - issues.py — issue types and tracking
    - tags.py — tag reading
    - isrc.py — ISRC handling
    - dedupe.py — duplicate detection within scans
    - constants.py — shared constants
    - archive.py — archive handling
- tests/scan/test_orchestrator.py (163 LOC) and tests/cli/test_scan_cli.py
  (116 LOC) already exist.

WHAT TO DO:
1. Read tagslut/scan/orchestrator.py in full. Understand its public API.
2. Read tests/scan/test_orchestrator.py and tests/cli/test_scan_cli.py to
   understand expected behavior.
3. Replace each stub function in tagslut/cli/scan.py with a real call to
   the orchestrator:
   - enqueue_scan() → use orchestrator to enqueue files from a root path
   - run_scan_job() → use orchestrator to execute a scan run
   - get_status_rows() → query scan session/run status from DB
   - get_issue_rows() → query issues from DB, filtered by severity
   - get_report_rows() → aggregate issue counts from DB
4. Add a --db option to scan commands that need database access.
5. Ensure the scan group remains hidden=True (it's not yet canonical).

CONSTRAINTS:
- Do NOT change the orchestrator module itself.
- Do NOT make scan group visible (keep hidden=True).
- Run existing scan tests — they must still pass.
- Run full suite: `poetry run pytest -x` — all tests pass.

ACCEPTANCE CRITERIA:
- `tagslut scan enqueue --root /some/dir --db test.db` actually enqueues files
- `tagslut scan status --db test.db` shows real data
- All existing scan tests pass
- Full test suite passes
```

---

## Prompt 5 — Deepen test coverage for `tagslut/policy/`

**Priority: MEDIUM**
**Branch: `test/policy-unit-tests`**

```
TASK: Add unit tests for tagslut/policy/ beyond the existing smoke test.

CONTEXT:
- tagslut/policy/ has 3 modules:
    - models.py: PolicyProfile, MatchRules, DurationRules, ExecutionRules
      dataclasses + ALLOWED_ACTIONS/COLLISION_POLICIES/MATCH_KINDS constants
    - loader.py: load_policy_profile(), list_policy_profiles(),
      PolicyValidationError — loads YAML policy files from config/policies/
    - lint.py: lint_policy_profile() — validates DJ-specific rules
- tests/core/test_policy_smoke.py (73 LOC) exists but only does import checks.
- tests/test_policy_decision_engine.py exists and tests the decide command flow,
  but doesn't unit-test the policy module directly.

WHAT TO DO:
1. Read all 3 policy modules in full.
2. Read the existing smoke test and decision engine test.
3. Check what policy YAML files exist: `ls config/policies/` or similar.
4. Create tests/policy/test_policy_models.py:
   - Test PolicyProfile.to_dict() round-trips
   - Test PolicyProfile.policy_id is deterministic
   - Test all frozen dataclass constraints (immutability)
   - Test ALLOWED_ACTIONS, ALLOWED_COLLISION_POLICIES, ALLOWED_MATCH_KINDS
     contain expected values
5. Create tests/policy/test_policy_loader.py:
   - Test load_policy_profile() with a real YAML file from config/policies/
   - Test load_policy_profile() with an invalid YAML → PolicyValidationError
   - Test list_policy_profiles() returns known profiles
   - Test load_builtin_policies() loads all without error
6. Create tests/policy/test_policy_lint.py:
   - Test lint_policy_profile() on a valid profile → empty list
   - Test lint_policy_profile() on a profile with bad DJ rules → non-empty list
   - Construct edge-case PolicyProfile objects to trigger each lint rule
7. Add tests/policy/__init__.py (empty).

CONSTRAINTS:
- Do NOT modify any source code in tagslut/policy/.
- Tests must not require external services or real music files.
- Use tmp_path fixtures for any file I/O.
- Run `poetry run pytest tests/policy/ -v` — all pass.
- Run `poetry run pytest -x` — full suite passes (274+ tests).

ACCEPTANCE CRITERIA:
- tests/policy/ directory has 3+ test files
- At least 15 new test functions total
- `poetry run pytest tests/policy/ -v` shows all green
- Full suite still passes
```

---

## Prompt 6 — Deepen test coverage for `tagslut/filters/`

**Priority: MEDIUM**
**Branch: `test/filters-unit-tests`**

```
TASK: Add unit tests for tagslut/filters/ beyond the existing smoke test.

CONTEXT:
- tagslut/filters/ has 3 modules:
    - identity_resolver.py: IdentityResolver class (resolves track identity via
      ISRC → provider IDs → fuzzy match chain), TrackIntent and ResolutionResult
      dataclasses. Constants: FUZZY_THRESHOLD=88, DURATION_TOLERANCE_S=2.0
    - macos_filters.py: MacOSFilters class with static methods to detect and
      filter macOS metadata files (.DS_Store, ._*, .Spotlight-V100, etc.)
    - gig_filter.py: parse_filter() function that converts filter expressions
      like "genre:techno bpm:128-145 dj_flag:true" into SQL WHERE clauses.
      FilterParseError exception. FILTER_COLUMN_MAP constant.
- tests/filters/test_filters_smoke.py (36 LOC) exists but only does imports.
- tests/test_filters.py exists — read it to see what's already covered.

WHAT TO DO:
1. Read all 3 filter modules and existing test files in full.
2. Create tests/filters/test_identity_resolver.py:
   - Create an in-memory SQLite DB with the tagslut schema (use
     tagslut.storage.schema.init_db)
   - Insert test rows with known ISRCs, provider IDs, paths
   - Test ISRC exact match → resolve returns existing path
   - Test Beatport ID match → resolve returns existing path
   - Test fuzzy match (artist + title + duration within tolerance)
   - Test no match → action is NEW
   - Test quality upgrade detection (candidate rank < existing rank)
   - Test quality skip (candidate rank >= existing rank)
3. Create tests/filters/test_macos_filters.py:
   - Test is_macos_metadata(".DS_Store") → True
   - Test is_macos_metadata("track.flac") → False
   - Test filter_files() removes macOS files from a list
   - Test count_filtered() returns correct counts
4. Create tests/filters/test_gig_filter.py:
   - Test parse_filter("genre:techno") → valid WHERE clause
   - Test parse_filter("bpm:128-145") → BETWEEN clause
   - Test parse_filter("dj_flag:true") → dj_flag = 1
   - Test parse_filter("genre:techno bpm:128-145") → combined AND
   - Test parse_filter("invalid:") → FilterParseError
   - Test all keys in FILTER_COLUMN_MAP produce valid SQL

CONSTRAINTS:
- Do NOT modify source code.
- Use in-memory SQLite for IdentityResolver tests.
- Run `poetry run pytest tests/filters/ -v` — all pass.
- Full suite passes.

ACCEPTANCE CRITERIA:
- tests/filters/ has 3+ test files
- At least 15 new test functions
- All green
```

---

## Prompt 7 — Deepen test coverage for `tagslut/metadata/`

**Priority: MEDIUM**
**Branch: `test/metadata-unit-tests`**

```
TASK: Add unit tests for the tagslut/metadata/ submodule.

CONTEXT:
- tagslut/metadata/ has 10 .py files. The key testable ones without external
  services are:
    - models/types.py: MatchConfidence, MetadataHealth enums; ProviderTrack,
      EnrichmentResult, LocalFileInfo dataclasses
    - models/precedence.py: precedence lists (DURATION_PRECEDENCE,
      BPM_PRECEDENCE, etc.)
    - genre_normalization.py: GenreNormalizer class with normalize_value(),
      choose_normalized(), apply_tags_to_file()
    - beatport_normalize.py: normalize_beatport_track(), BeatportTrack,
      extract_beatport_track_info(), beatport_track_to_dict()
    - auth.py: TokenManager, TokenInfo (can test token expiry logic, template
      init, status — but NOT actual OAuth flows)
- tests/core/test_metadata_smoke.py (47 LOC) exists — only import checks.

WHAT TO DO:
1. Read all metadata modules listed above.
2. Create tests/metadata/__init__.py (empty).
3. Create tests/metadata/test_metadata_models.py:
   - Test MatchConfidence enum values
   - Test MetadataHealth enum values
   - Test ProviderTrack construction with minimal fields
   - Test EnrichmentResult construction
   - Test LocalFileInfo construction
4. Create tests/metadata/test_genre_normalization.py:
   - Test GenreNormalizer.normalize_value() with known genre mappings
   - Test choose_normalized() picks correct genre from tag dict
   - Test PROTECTED_COMPOUND genres are not split
   - Test edge cases: empty strings, None values
5. Create tests/metadata/test_beatport_normalize.py:
   - Build sample Beatport JSON payloads (look at the function signatures
     for expected structure)
   - Test normalize_beatport_track() produces correct BeatportTrack
   - Test extract_beatport_track_info() returns expected tuple
   - Test beatport_track_to_dict() round-trips
6. Create tests/metadata/test_token_manager.py:
   - Test TokenInfo.is_expired with past/future timestamps
   - Test TokenManager.init_template() creates a file (use tmp_path)
   - Test TokenManager.status() returns dict with provider keys
   - Do NOT test actual OAuth flows or network calls

CONSTRAINTS:
- No network calls. No real music files.
- Mock mutagen/file access where needed.
- Use tmp_path for any file I/O.
- Do NOT modify source code.
- Run `poetry run pytest tests/metadata/ -v` — all pass.

ACCEPTANCE CRITERIA:
- tests/metadata/ has 4+ test files
- At least 20 new test functions
- Zero test failures
- Full suite passes
```

---

## Prompt 8 — Implement `tagslut gig build` end-to-end with GigBuilder

**Priority: HIGH (DJ workflow)**
**Branch: `feat/gig-builder-e2e`**

```
TASK: Complete the GigBuilder implementation so `tagslut gig build` works
end-to-end: filter inventory → ensure MP3 in DJ pool → export to USB →
write Rekordbox DB → print manifest.

CONTEXT:
- tagslut/cli/commands/gig.py (106 LOC) is fully wired. It calls:
    from tagslut.exec.gig_builder import GigBuilder
  and invokes builder.build(name, filter_expr, usb, dry_run=dry_run).

- tagslut/exec/gig_builder.py exists (139 LOC) — read it to see current state.

- tagslut/filters/gig_filter.py has parse_filter() which converts filter
  expressions to SQL WHERE clauses.

- tagslut/exec/usb_export.py (154 LOC) has copy_to_usb(), scan_source(),
  write_manifest(), write_rekordbox_db() — these work for `tagslut export usb`.

- tagslut/exec/transcoder.py exists — read it for FLAC→MP3 transcoding.

- tagslut/metadata/rekordbox_sync.py has sync_from_usb() for reading back
  BPM/key from Pioneer USB.

- The inventory DB has these DJ fields (from migration 0002):
  dj_flag, bpm, key_camelot, isrc, dj_pool_path, last_exported_usb,
  quality_rank, genre, canonical_genre, canonical_bpm, canonical_label

WHAT TO DO:
1. Read gig_builder.py, gig_filter.py, usb_export.py, transcoder.py in full.
2. The GigBuilder.build() method should:
   a) Call parse_filter(filter_expr) to get SQL WHERE clause
   b) Query inventory DB for matching tracks
   c) For each track: check if MP3 exists at dj_pool_path
      - If not: transcode FLAC master → MP3 in dj_pool_dir
      - Update dj_pool_path in DB
   d) Copy MP3s to USB under MUSIC/{crate_name}/ directory
   e) Write Rekordbox PIONEER/ database using pyrekordbox
   f) Write a gig manifest file to USB
   g) Record the gig set in a `gig_sets` table (name, track_count,
      exported_at, usb_path, filter_expr)
   h) Return a GigResult with summary() and errors list
3. Create the `gig_sets` table in tagslut/storage/schema.py init_db() if it
   doesn't exist (use CREATE TABLE IF NOT EXISTS).
4. Add tests in tests/dj/test_gig_builder.py:
   - Test with in-memory DB, mock FLAC files (use tmp_path)
   - Test filter→query→transcode→copy flow
   - Test dry_run produces summary but no file writes

CONSTRAINTS:
- Use existing usb_export.py functions for USB operations.
- Use existing transcoder.py for FLAC→MP3.
- Use pyrekordbox for Rekordbox DB writes (it's already a dependency).
- Move-only semantics: FLAC masters are NEVER modified. MP3s are derived copies.
- Run `poetry run pytest -x` — full suite passes.

ACCEPTANCE CRITERIA:
- `tagslut gig build "Test Set" --filter "dj_flag:true" --usb /tmp/usb --db test.db`
  produces tracks on USB with PIONEER/ database
- Dry run mode prints plan without writing
- gig_sets table records each build
- At least 5 new tests in tests/dj/test_gig_builder.py
```

---

## Prompt 9 — Implement pre-download resolution in `tagslut intake`

**Priority: HIGH (core workflow)**
**Branch: `feat/pre-download-resolution`**

```
TASK: Implement the pre-download resolution pipeline described in REPORT.md
so `tagslut intake` can diff a playlist against the inventory before
downloading, producing a manifest of NEW/UPGRADE/SKIP decisions.

CONTEXT:
- REPORT.md describes the core workflow:
    receive playlist URL → resolve track IDs → diff against inventory
    → build manifest: NEW (download), UPGRADE (download+replace), SKIP
    → execute download only for NEW + UPGRADE

- tagslut/filters/identity_resolver.py ALREADY implements:
    - IdentityResolver class with resolve(intent, candidate_rank) method
    - Resolution chain: ISRC → Beatport ID → Tidal ID → Qobuz ID → fuzzy
    - TrackIntent and ResolutionResult dataclasses
    - Quality rank comparison logic

- tagslut/cli/commands/intake.py (23 LOC) is currently a thin wrapper.

- The `tools/get` script routes URLs to tools/tiddl or tools/beatportdl.

- The quality rank model (REPORT.md):
    1=FLAC 32bit+/DSD, 2=FLAC 24/96+, 3=FLAC 24/44.1, 4=FLAC 16/44.1,
    5=AIFF/WAV 16bit, 6=MP3 320, 7=MP3 <320

WHAT TO DO:
1. Read tagslut/filters/identity_resolver.py in full.
2. Read tagslut/cli/commands/intake.py in full.
3. Read tagslut/metadata/beatport_normalize.py to understand how Beatport
   track metadata is structured (ISRC, BPM, etc.)
4. Create tagslut/core/download_manifest.py:
   - DownloadManifest class that holds lists of NEW/UPGRADE/SKIP decisions
   - ManifestEntry dataclass: track_intent, action, reason, existing_path?
   - build_manifest(track_intents, conn) → DownloadManifest
     Uses IdentityResolver to check each intent against inventory
   - DownloadManifest.summary() → human-readable summary string
   - DownloadManifest.to_json(path) → persist manifest as JSON
5. Add `intake resolve` subcommand to intake.py:
   - Takes a playlist URL or file of track metadata (JSONL)
   - Resolves each track against inventory
   - Prints manifest: "12 new, 3 upgrades, 25 skipped"
   - Writes manifest JSON to artifacts/
6. Add `intake run` to use the manifest: only download NEW + UPGRADE tracks.
   For now, print the download commands that WOULD be run (actual download
   integration with tiddl/bpdl is a follow-up).

CONSTRAINTS:
- Use existing IdentityResolver — do NOT rewrite resolution logic.
- Do NOT actually call download tools yet (just generate the manifest).
- The manifest must be deterministic and serializable to JSON.
- Run `poetry run pytest -x` — all tests pass.

ACCEPTANCE CRITERIA:
- `tagslut intake resolve --db inventory.db --input tracks.jsonl` produces
  a manifest with NEW/UPGRADE/SKIP counts
- Manifest JSON is written to artifacts/
- DownloadManifest has unit tests (at least 8 test functions)
- Full test suite passes
```

---

## Prompt 10 — Add `tagslut index` deep tests for DJ flag commands

**Priority: MEDIUM**
**Branch: `test/index-dj-commands`**

```
TASK: Add integration tests for the DJ flag commands in tagslut index:
dj-flag, dj-autoflag, dj-status.

CONTEXT:
- tagslut/cli/commands/index.py lines 64-207 implement 3 DJ commands:
    - `index dj-flag TARGET --set true/false --db DB` — flag a single track
    - `index dj-autoflag --genre X --bpm LO-HI --label X --db DB` — bulk flag
    - `index dj-status --db DB` — show DJ pool status counts
- These are direct implementations (not shims) that use sqlite3 directly.
- tagslut/storage/schema.py has init_db() which creates tables.
- tagslut/migrations/0002_add_dj_fields.py adds the DJ columns.

WHAT TO DO:
1. Read index.py DJ commands (lines 64-207) in full.
2. Create tests/cli/test_index_dj_commands.py:
   - Use Click's CliRunner for testing
   - Create an in-memory or tmp_path SQLite DB with init_db() + migration
   - Insert test rows with known genres, BPMs, labels, ISRCs

   Tests for dj-flag:
   - Flag by file path → row updated
   - Flag by ISRC → row(s) updated
   - Unflag (--set false) → row updated
   - Flag nonexistent target → 0 rows updated

   Tests for dj-autoflag:
   - Filter by genre → correct rows flagged
   - Filter by BPM range → correct rows flagged
   - Filter by label → correct rows flagged
   - Combined filters → intersection flagged
   - Invalid BPM range format → error message
   - No filters provided → error message

   Tests for dj-status:
   - Empty DB → all zeros
   - DB with flagged/unflagged mix → correct counts
   - DB with exported tracks → correct exported count

CONSTRAINTS:
- Do NOT modify source code.
- Use tmp_path for DB files.
- Use Click CliRunner for CLI invocation.
- Run `poetry run pytest tests/cli/test_index_dj_commands.py -v` — all pass.
- Full suite passes.

ACCEPTANCE CRITERIA:
- At least 12 new test functions
- All 3 DJ commands have test coverage
- Full test suite passes
```

---

## Implementation Order

| Order | Prompt | Status |
|---|---|---|
| 0 | Close stale issues | **DONE** |
| 1 | Inline _mgmt shim | **DONE** |
| 2 | Inline _metadata shim | **DONE** |
| 3 | pyproject.toml cleanup | **DONE** |
| 4 | Scan orchestrator | **DONE** |
| 5 | Policy unit tests | **DONE** |
| 6 | Filters unit tests | **DONE** |
| 7 | Metadata unit tests | **DONE** |
| 8 | Gig builder E2E | **DONE** |
| 9 | Pre-download resolution | **DONE** |
| 10 | Index DJ command tests | **DONE** |

**All 11 prompts completed. 375 tests passing as of 2026-03-01.**
