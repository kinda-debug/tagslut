Here are the Round 3 prompts, derived directly from the audit findings. All prompts in Rounds 1 and 2 are marked complete as of 2026-03-01 (375 tests passing) , so these target the remaining gaps.

***

## Prompt 0 — Manual Gate Closures

> Not a Codex task — do these by hand.

**Phase 5 open gates:**
```bash
# 1. Verify no retired commands in help output
poetry run tagslut --help | grep -E "scan|recommend|apply|promote|quarantine|mgmt|metadata|recover"
 Expected: no output. If any appear, that's a bug — file an issue.

# 2. Start the two-week post-cutover soak clock (log today's date)
echo "Soak started: $(date -u)" >> artifacts/phase5_soak_log.txt
poetry run pytest tests -x -q >> artifacts/phase5_soak_log.txt 2>&1
```

**Record KPI baselines from the last 30 days of artifacts:**
```bash
# Approximate queries to run against your live DB
sqlite3 ~/music.db "SELECT COUNT(*) FROM move_execution WHERE outcome='success';"
sqlite3 ~/music.db "SELECT COUNT(*) FROM move_execution WHERE outcome='failed';"
sqlite3 ~/music.db "SELECT COUNT(*) FROM files WHERE dj_flag=1;"
sqlite3 ~/music.db "SELECT COUNT(*) FROM files WHERE duration_status != 'ok' AND dj_flag=1;"
# Paste results into docs/REDESIGN_TRACKER.md under KPI Baselines
```

**Assign program owners** in `docs/REDESIGN_TRACKER.md` — every lead role is still `TBD`.

***

## Prompt 1 — Bump Version to 3.0.0 and Fix Phase 5 Help Gate

**Priority: HIGH (immediate)**
**Branch: `chore/v3-release-markers`**

```
TASK: Bump the package version to 3.0.0, close the open Phase 5 help-gate
verification, and update the description string to match v2+ framing.

CONTEXT:
- pyproject.toml still declares version = "2.0.0" despite all V3 phases
  being complete per docs/REDESIGN_TRACKER.md.
- The project description still says "recovery-first music library
  deduplication" — recovery framing was retired in REPORT.md.
- docs/PHASE5_LEGACY_DECOMMISSION.md has an unchecked gate:
  [ ] tagslut --help output contains no references to retired wrappers
- The retired wrappers are: scan, recommend, apply, promote, quarantine,
  mgmt, metadata, recover.

WHAT TO DO:
1. In pyproject.toml:
   - Change version = "2.0.0" → version = "3.0.0"
   - Change description to: "Tagslut: hi-res music library management and
     DJ pool orchestration toolkit for audiophile DJs."
   - No other changes.

2. Audit tagslut/cli/main.py for any add_command() calls that register
   retired commands at the top-level CLI. If found, remove them. If scan_group
   is still registered (check line ~84), remove that import and add_command call.

3. Write a test in tests/test_cli_command_interface.py:
   def test_no_retired_commands_in_cli():
       from tagslut.cli.main import cli
       RETIRED = {"scan", "recommend", "apply", "promote", "quarantine",
                  "mgmt", "metadata", "recover", "dedupe"}
       registered = set(cli.commands.keys())
       assert registered.isdisjoint(RETIRED), \
           f"Retired commands still registered: {registered & RETIRED}"

4. In docs/PHASE5_LEGACY_DECOMMISSION.md, check the box:
   [x] tagslut --help output contains no references to retired wrappers

CONSTRAINTS:
- Do NOT change any behavior, only version string + description + gate close.
- Run poetry run pytest -x — all tests pass.
- Run poetry run tagslut --help and paste the command list into the commit
  message body.

ACCEPTANCE CRITERIA:
- pyproject.toml has version = "3.0.0"
- test_no_retired_commands_in_cli passes
- poetry run tagslut --help shows only: intake, index, decide, execute,
  verify, report, auth (plus any hidden internal commands)
- PHASE5_LEGACY_DECOMMISSION.md gate is checked
```

***

## Prompt 2 — Create `docs/README.md` Documentation Index

**Priority: HIGH (broken link)**
**Branch: `docs/readme-index`**

```
TASK: Create docs/README.md as the documentation index advertised in the
root README.md ("See docs/README.md for the full documentation index").

CONTEXT:
- Root README.md line: "See `docs/README.md` for the full documentation index."
- docs/README.md does not exist.
- The docs/ directory contains 19 files. Some are active, some are archived
  in docs/archive/, some are implementation plans for phases now complete.

Active docs (include in index):
  docs/ARCHITECTURE.md
  docs/WORKFLOWS.md
  docs/OPERATIONS.md
  docs/TROUBLESHOOTING.md
  docs/DJ_WORKFLOW.md
  docs/DJ_REVIEW_APP.md
  docs/SCRIPT_SURFACE.md
  docs/SURFACE_POLICY.md
  docs/REDESIGN_TRACKER.md
  docs/PHASE5_LEGACY_DECOMMISSION.md
  docs/PROJECT.md
  docs/PROGRESS_REPORT.md
  docs/CODEX_PROMPTS.md
  docs/CODEX_PROMPTS_ROUND2.md

Historical/archived (list but mark as reference only):
  docs/SCANNER_V1.md
  docs/SCANNER_V1_PROGRESS.md
  docs/IMPLEMENTATION_PLAN_DJ_GIG.md
  docs/IMPLEMENTATION_PLAN_SCANNER_V1.md
  docs/TESTS_RETIRED.md
  docs/PHASE5_LEGACY_DECOMMISSION.md (already in active above)

WHAT TO DO:
1. Create docs/README.md with sections:
   ## Operator Docs (start here)
   - WORKFLOWS.md — end-to-end operating procedures
   - OPERATIONS.md — day-to-day commands and recipes
   - DJ_WORKFLOW.md — DJ pool build and USB sync
   - TROUBLESHOOTING.md — known issues and fixes

   ## Architecture
   - ARCHITECTURE.md — system design and data flow
   - SCRIPT_SURFACE.md — canonical command map
   - SURFACE_POLICY.md — surface governance rules

   ## Project Status
   - PROJECT.md — project overview and goals
   - PROGRESS_REPORT.md — current state and pending work
   - REDESIGN_TRACKER.md — V3 program status and decisions log

   ## DJ Tools
   - DJ_REVIEW_APP.md — local DJ review web app

   ## Implementation History (reference only)
   - PHASE5_LEGACY_DECOMMISSION.md — Phase 5 runbook (completed)
   - CODEX_PROMPTS.md — Round 1 Codex implementation record
   - CODEX_PROMPTS_ROUND2.md — Round 2 Codex implementation record

2. Write a test in tests/test_repo_structure.py (or a new file):
   def test_docs_readme_exists():
       assert Path("docs/README.md").exists()

ACCEPTANCE CRITERIA:
- docs/README.md exists and has all active docs linked
- All linked paths are valid (no 404s within the repo)
- test_docs_readme_exists passes
- Full test suite passes
```

***

## Prompt 3 — Replace `CHANGELOG.md` with a Real Project Changelog

**Priority: MEDIUM**
**Branch: `docs/proper-changelog`**

```
TASK: Replace the root CHANGELOG.md with a proper semver project changelog.
Move the current content (which is a classifier script changelog, not a
project changelog) to docs/archive/.

CONTEXT:
- CHANGELOG.md is entirely about the DJ track classification script v2
  (scripts/classify_tracks_sqlite.py). It has nothing to do with the
  project's release history.
- There is no project-level changelog anywhere in the repo.
- The project has been through 5 redesign phases and is now at v3.0.0.

WHAT TO DO:
1. Move CHANGELOG.md → docs/archive/CLASSIFY_V2_CHANGELOG.md
   Add a comment at the top: "# Archived: DJ Track Classification Script v2 Changelog"

2. Create a new CHANGELOG.md at root following Keep a Changelog format:
   # Changelog

   All notable changes to this project are documented here.
   Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
   Versioning: [Semantic Versioning](https://semver.org/)

   ## [3.0.0] — 2026-03-02
   ### Added
   - Canonical v3 CLI surface: intake, index, decide, execute, verify, report, auth
   - Centralized move executor (tagslut.exec.engine) with MoveReceipt verification
   - Policy engine (tagslut.policy) with deterministic planning and plan hashing
   - V3 data model: asset_file, track_identity, asset_link, provenance_event,
     move_plan, move_execution tables
   - DJ pipeline: gig builder, USB export, transcode, Rekordbox XML export
   - Pre-download identity resolution (ISRC → provider IDs → fuzzy fallback)
   - OneTagger ISRC enrichment wrappers (tools/tag, tag-build, tag-run)
   - Classification v2: genre fallback + soft scoring (scripts/classify_tracks_sqlite.py)
   ### Changed
   - Version bumped from 2.0.0 to 3.0.0
   - Project description updated to management-first framing
   ### Removed
   - Legacy CLI wrappers: scan, recommend, apply, promote, quarantine, mgmt,
     metadata, recover (all retired per Phase 5)
   - Recovery-era framing and documentation

   ## [2.0.0] — 2025-02-01
   ### Changed
   - Rebrand from dedupe to tagslut
   - Recovery phase declared complete; library rebuilt

3. Update scripts/check_cli_docs_consistency.py or add a new test that
   asserts docs/archive/CLASSIFY_V2_CHANGELOG.md exists (so the move is
   verified by CI).

ACCEPTANCE CRITERIA:
- Root CHANGELOG.md follows Keep a Changelog format
- docs/archive/CLASSIFY_V2_CHANGELOG.md exists with original content
- Full test suite passes
```

***

## Prompt 4 — Archive `tagslut/recovery/` and `tagslut/scan/` Packages

**Priority: MEDIUM**
**Branch: `refactor/archive-retired-subpackages`**

```
TASK: Remove tagslut/recovery/ and tagslut/scan/ from the live package and
archive their implementations under legacy/. These commands were retired in
Phase 5 but their source trees remain in the active package namespace.

CONTEXT:
- REPORT.md: "Not a recovery tool (that phase is over — see legacy/ for
  recovery-era artifacts)"
- tagslut/recovery/ and tagslut/scan/ still exist as importable packages
- Their tests/recovery/ and tests/scan/ counterparts also exist
- docs/TESTS_RETIRED.md exists — check it for guidance on what's already
  been formally retired
- tagslut/cli/scan.py imports from tagslut.scan — check the import chain
  before deleting

WHAT TO DO:
1. Read docs/TESTS_RETIRED.md and tagslut/cli/scan.py to understand
   full import dependencies.

2. For tagslut/recovery/:
   a. Check all import sites: grep -r "from tagslut.recovery" tagslut/ tests/
   b. If still imported anywhere: stub all public symbols with a
      DeprecatedModule class that raises ImportError with a migration message
   c. If not imported anywhere: move the entire directory to
      legacy/tagslut_recovery/
   d. If tests/recovery/ tests are still meaningful, keep them but mark with
      @pytest.mark.skip(reason="recovery module archived") OR delete them
      and add a note to docs/TESTS_RETIRED.md

3. For tagslut/scan/:
   a. Check all import sites: grep -r "from tagslut.scan" tagslut/ tests/
   b. tagslut/cli/scan.py DOES import from tagslut.scan — read it carefully
   c. If scan CLI group is still registered (after Prompt 1), it must be
      removed FIRST (do Prompt 1 before this)
   d. Once scan is not CLI-registered, move tagslut/scan/ → legacy/tagslut_scan/
   e. Stub tagslut/scan/__init__.py with an ImportError DeprecatedModule
      to catch any accidental imports

4. Update tests/test_repo_structure.py:
   - Add assertion that tagslut/recovery/ does NOT exist (or is stubbed)
   - Add assertion that tagslut/scan/ does NOT exist (or is stubbed)

5. Update docs/TESTS_RETIRED.md to record the archival.

CONSTRAINTS:
- Do NOT delete tests/ subfolders — move to tests/archive/ with retirement note
- Preserve all moved code in legacy/ so git history is traceable
- Run poetry run pytest -x — all non-skip tests pass
- Run poetry run python -c "import tagslut" — no import errors

ACCEPTANCE CRITERIA:
- tagslut/recovery/ is either absent or a DeprecatedModule stub
- tagslut/scan/ is either absent or a DeprecatedModule stub
- No active (non-skipped) tests import from tagslut.recovery or tagslut.scan
- Full test suite passes
```

***

## Prompt 5 — Promote `classification_v2` to Primary in Live DB

**Priority: HIGH (operational)**
**Branch: `feat/classify-v2-promotion-script`**

```
TASK: Create a safe, idempotent promotion script that swaps classification_v2
→ primary classification in the inventory DB, and wire it as a tagslut subcommand.

CONTEXT:
- CHANGELOG.md (now in docs/archive/CLASSIFY_V2_CHANGELOG.md) documents the
  v2 classification system and its promotion steps.
- The promotion steps are currently documented as manual SQL snippets.
- The DB has two columns: classification (v1) and classification_v2.
- SQLite ≥ 3.25 supports RENAME COLUMN which atomically swaps them.
- scripts/classify_tracks_sqlite.py is the classification engine.
- The promotion has not been executed — both columns still exist in the schema.

WHAT TO DO:
1. Create scripts/promote_classification_v2.py:
   - Check SQLite version: use RENAME COLUMN path if ≥ 3.25, classic migration
     if < 3.25 (copy table approach)
   - Idempotent: check if classification_v2 column exists before running;
     if already promoted (column absent), print "Already promoted" and exit 0
   - Backup: copy DB to DB.backup before any changes
   - After swap: run verification queries (distribution check, genre_blank%)
   - Check tripwires: remove% > 80% → abort with error; genre_blank% > 20% → abort
   - Print final distribution summary
   - Commit or rollback atomically

2. Add CLI entrypoint as `tagslut index promote-classification`:
   In tagslut/cli/commands/index.py, add:
   @index.command("promote-classification")
   @click.option("--db", required=True, help="Path to inventory DB")
   @click.option("--dry-run", is_flag=True, default=False)
   def index_promote_classification(db, dry_run):
       """Promote classification_v2 to primary classification column."""
       ...

3. Add tests in tests/test_classify_promote.py:
   - Test idempotent: run twice → second run is a no-op
   - Test dry-run: no changes to DB
   - Test SQLite ≥ 3.25 path (mock sqlite_version if needed)
   - Test tripwire fires when remove% > 80%
   - Test successful promotion → column renamed correctly

CONSTRAINTS:
- Always backup before modifying. Backup path = original path + ".backup".
- Use transactions. Rollback on any failure.
- Never truncate or delete data.
- Run poetry run pytest tests/test_classify_promote.py -v — all pass.
- Full suite passes.

ACCEPTANCE CRITERIA:
- tagslut index promote-classification --db test.db --dry-run prints plan
- tagslut index promote-classification --db test.db performs swap atomically
- Idempotent second run prints "Already promoted" and exits 0
- All new tests pass
```

***

## Prompt 6 — Resolve Flask Dependency: Wire DJ Review App or Remove

**Priority: MEDIUM**
**Branch: `feat/dj-review-cli` OR `chore/remove-flask-dep`**

```
TASK: Resolve the open architecture decision about the Flask web UI.
tools/dj_review_app.py (60KB) exists but Flask is only an optional dependency
with no canonical CLI entry point. Either wire it in or remove it.

CONTEXT (read these before deciding):
- tools/dj_review_app.py is a 60KB Flask app for local DJ track review
- pyproject.toml has: [project.optional-dependencies] web = ["flask>=3.1.2,<4.0.0"]
- docs/DJ_REVIEW_APP.md describes its purpose: local DJ pool browser with
  OK/Not OK verdicts and auto-verdict support
- REPORT.md flags: "Flask web UI — declared but never implemented. Decision
  needed: build it or remove the dependency."
- The app DOES exist (tools/dj_review_app.py) so "never implemented" was
  written before the tools/ app existed

DECISION (make this call):
Since the app exists and is 60KB, WIRE IT IN:

WHAT TO DO:
1. Read tools/dj_review_app.py in full to understand its startup arguments
   (DB path, port, host, etc.)

2. Add tagslut report dj-review subcommand in tagslut/cli/commands/report.py:
   @report.command("dj-review")
   @click.option("--db", required=True, help="Inventory DB path")
   @click.option("--port", default=5000, help="Port to listen on")
   @click.option("--host", default="127.0.0.1", help="Host to bind")
   @click.option("--open-browser", is_flag=True, default=True)
   def report_dj_review(db, port, host, open_browser):
       """Launch local DJ track review web app."""
       try:
           from tagslut._web.review_app import run_review_app
       except ImportError:
           raise click.ClickException(
               "Flask is required. Install with: pip install tagslut[web]"
           )
       run_review_app(db=db, port=port, host=host, open_browser=open_browser)

3. Move tools/dj_review_app.py → tagslut/_web/review_app.py
   Wrap the startup logic in a run_review_app(db, port, host, open_browser) function.
   Keep the tools/dj_review_app.py as a thin shim that calls run_review_app()
   for backward compat.

4. Move the Flask dep from optional to a proper optional group:
   In pyproject.toml rename [project.optional-dependencies] web to include
   a comment: "# Install with: pip install tagslut[web]"

5. Update docs/DJ_REVIEW_APP.md launch instructions from "python tools/dj_review_app.py"
   to "tagslut report dj-review --db music.db"

6. Add a test in tests/test_cli_command_interface.py that verifies
   report dj-review exists in the CLI even without Flask installed
   (it should fail gracefully with ImportError guidance, not NameError).

ACCEPTANCE CRITERIA:
- tagslut report dj-review --help works without Flask installed
- tagslut report dj-review --db test.db launches app when Flask is installed
- ImportError produces a helpful install instruction, not a traceback
- docs/DJ_REVIEW_APP.md reflects new launch command
- Full test suite passes
```

***

## Prompt 7 — Zone Model Migration: GOOD/BAD/QUARANTINE → LIBRARY/DJPOOL/ARCHIVE

**Priority: MEDIUM**
**Branch: `feat/zone-model-migration`**

```
TASK: Execute the zone model migration documented as an open architecture
decision in REPORT.md. Replace legacy zone values GOOD/BAD/QUARANTINE with
LIBRARY/DJPOOL/ARCHIVE across the schema, code, and policies.

CONTEXT:
- REPORT.md: "Zone model — legacy zones (GOOD/BAD/QUARANTINE) should be
  replaced with (LIBRARY/DJPOOL/ARCHIVE) to match the new management framing"
- Grep the codebase for current zone usage:
    grep -r "GOOD\|BAD\|QUARANTINE" tagslut/ --include="*.py" | grep -v test
  to understand all sites before changing anything.
- The DB column is likely `zone` in the files table.
- config/policies/ YAML files may reference zone values.

WHAT TO DO:
1. Run the grep audit above and list every file + line that references
   GOOD, BAD, or QUARANTINE as zone values.

2. Create a migration: tagslut/storage/migrations/0004_zone_model_v2.py
   (or .sql) that:
   UPDATE files SET zone = 'LIBRARY' WHERE zone = 'GOOD';
   UPDATE files SET zone = 'ARCHIVE' WHERE zone = 'BAD';
   UPDATE files SET zone = 'ARCHIVE' WHERE zone = 'QUARANTINE';
   # Do NOT delete data — BAD and QUARANTINE both map to ARCHIVE
   # Add a CHECK constraint to block old zone values going forward

3. In tagslut/core/ (wherever zone constants are defined):
   - Replace ZONE_GOOD/ZONE_BAD/ZONE_QUARANTINE with ZONE_LIBRARY/ZONE_ARCHIVE/ZONE_DJPOOL
   - Keep old names as deprecated aliases: ZONE_GOOD = ZONE_LIBRARY  # deprecated

4. Update all policy YAML files in config/policies/ that reference zones.

5. Update tagslut/exec/engine.py and any other executor paths that use zone
   string literals.

6. Add tests in tests/storage/test_zone_migration.py:
   - Test migration converts GOOD → LIBRARY, BAD → ARCHIVE, QUARANTINE → ARCHIVE
   - Test idempotent re-run (migration runner skip)
   - Test CHECK constraint rejects 'GOOD' after migration

CONSTRAINTS:
- Never drop data. BAD and QUARANTINE both become ARCHIVE.
- Use the migration runner from Prompt 5 of Round 2 (tagslut/storage/migration_runner.py).
- Provide rollback (down() function) that maps back.
- Run poetry run pytest -x — all tests pass.

ACCEPTANCE CRITERIA:
- No live code references ZONE_GOOD/BAD/QUARANTINE as primary constants
- Migration is idempotent and has a down() rollback
- Zone tests pass
- Full suite passes
```

***

## Prompt 8 — ISRC as Primary DB Key: Migration and Query Layer Update

**Priority: HIGH (architectural — enables correct intake)**
**Branch: `feat/isrc-primary-key`**
**Depends on: zone migration merged cleanly**

```
TASK: Execute the ISRC-as-primary-key schema migration described in REPORT.md
and update the query layer to use ISRC as the primary track identity column.

CONTEXT:
- REPORT.md: "ISRC as primary DB key — schema migration required (tagslut/migrations/)"
- ISRC is the canonical identity for the identifier resolution chain
  (tagslut/filters/identity_resolver.py priority order: ISRC first)
- Currently, the files table uses an auto-increment INTEGER id as primary key
  and ISRC is a secondary TEXT column (nullable).
- The V3 tables (track_identity, asset_link) already use ISRC-centric design.
- The goal is NOT to change the files table PK (that's risky) but to:
  a) Ensure ISRC has a UNIQUE INDEX on the files table
  b) Ensure all lookups go through ISRC first (not just text search)
  c) Ensure tagslut/storage/queries.py uses ISRC for identity lookups

WHAT TO DO:
1. Read tagslut/storage/queries.py in full. Find all functions that look up
   tracks — identify which use ISRC vs which use path/filename/fuzzy.

2. Create tagslut/storage/migrations/0005_isrc_unique_index.py:
   def up(conn):
       # Create unique index on ISRC where non-null
       conn.execute("""
           CREATE UNIQUE INDEX IF NOT EXISTS idx_files_isrc
           ON files(isrc) WHERE isrc IS NOT NULL AND TRIM(isrc) != ''
       """)
   def down(conn):
       conn.execute("DROP INDEX IF EXISTS idx_files_isrc")

3. In tagslut/storage/queries.py, add or update:
   def get_file_by_isrc(conn, isrc: str) -> Optional[sqlite3.Row]:
       """Primary identity lookup — use this before any other lookup."""
       return conn.execute(
           "SELECT * FROM files WHERE isrc = ?", (isrc,)
       ).fetchone()

4. Update tagslut/filters/identity_resolver.py IdentityResolver.resolve():
   - Ensure the ISRC branch calls get_file_by_isrc() (not a LIKE query)
   - If already using get_file_by_isrc(), confirm it uses the indexed column

5. Update tagslut/core/download_manifest.py (from Round 1 Prompt 9):
   - Ensure ManifestEntry.action=SKIP fires correctly via ISRC index lookup

6. Add tests in tests/storage/test_isrc_queries.py:
   - Insert track with ISRC; get_file_by_isrc returns it
   - Insert track without ISRC; get_file_by_isrc returns None
   - Attempt to insert duplicate ISRC → IntegrityError
   - get_file_by_isrc with None → returns None safely

CONSTRAINTS:
- Do NOT change the files table PRIMARY KEY (too risky without full ORM).
- Partial unique index (WHERE isrc IS NOT NULL) is safe — multiple rows
  can have NULL isrc.
- Run poetry run pytest -x — all tests pass.

ACCEPTANCE CRITERIA:
- UNIQUE INDEX on files(isrc) exists after migration
- get_file_by_isrc() uses the indexed column
- Duplicate ISRC insert raises IntegrityError
- All tests pass
```

***

## Implementation Order

| Order | Prompt | Priority |
|---|---|---|
| 0 | Manual gate closures + KPI baselines | Immediate |
| 1 | Version bump to 3.0.0 + help gate | High |
| 2 | Create docs/README.md | High |
| 3 | Replace CHANGELOG.md | Medium |
| 4 | Archive recovery/ and scan/ packages | Medium |
| 5 | classification_v2 promotion script | High |
| 6 | Flask/DJ Review App wire-in | Medium |
| 7 | Zone model migration | Medium |
| 8 | ISRC primary key migration | High |

Prompts 1–5 are safe to run in parallel. Prompt 7 should precede Prompt 8 since both touch the schema layer and a clean migration history prevents ordering conflicts.
