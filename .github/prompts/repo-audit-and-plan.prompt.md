You are an expert Python/CLI engineer doing a full read-only audit of the tagslut
repository. Your goal: read every meaningful file, then produce a single prioritised
action plan written to docs/ACTION_PLAN.md.

No code changes. No commits. Read → synthesise → write one file.

SKIP ENTIRELY — do not read or list:
- artifacts/           (1000+ timestamped run outputs — not docs)
- output/              (600+ precheck/intake run CSVs and MDs — not docs)
- postman/sdks/        (generated SDK code — not relevant)
- docs/archive/        (archived/superseded — not current state)
- .venv/               (Python virtualenv)
- __pycache__/         (compiled bytecode)
- .git/                (git internals)

---

## PART 1 — Read everything, in this order

### A. Agent contracts (read first — these govern all behaviour)
- AGENT.md
- CLAUDE.md
- .codex/CODEX_AGENT.md
- .codex/CODEX_BOOTSTRAP_REPORT.md
- .codex/CODEX_PROMPTS.md
- .codex/REPO_SURFACE.md
- .github/copilot-instructions.md
- docs/PROJECT_DIRECTIVES.md

### B. Project state
- docs/ROADMAP.md
- docs/PROGRESS_REPORT.md
- docs/PHASE1_STATUS.md
- CHANGELOG.md
- docs/CLEANUP_MANIFEST.md
- docs/REDESIGN_TRACKER.md

### C. Architecture and schema
- docs/ARCHITECTURE.md
- docs/CORE_MODEL.md
- docs/DB_V3_SCHEMA.md
- docs/INGESTION_PROVENANCE.md
- docs/MULTI_PROVIDER_ID_POLICY.md
- docs/SURFACE_POLICY.md
- docs/SCRIPT_SURFACE.md
- docs/ZONES.md
- docs/contracts/README.md
- docs/contracts/metadata_architecture.md
- docs/contracts/metadata_row_contracts.md
- docs/contracts/provider_matching.md
- docs/architecture/V3_IDENTITY_HARDENING.md

### D. Workflows and operations
- docs/WORKFLOWS.md
- docs/OPERATIONS.md
- docs/TROUBLESHOOTING.md
- docs/CREDENTIAL_MANAGEMENT.md
- docs/CREDENTIAL_MANAGEMENT_AUDIT.md
- docs/DJ_PIPELINE.md
- docs/DJ_POOL.md
- docs/DJ_WORKFLOW.md
- docs/DJ_REVIEW_APP.md
- docs/PHASE5_LEGACY_DECOMMISSION.md
- docs/operations/V3_IDENTITY_HARDENING_RUNBOOK.md
- docs/gig/GIG_EXECUTION_PLAN_v3.3.md
- docs/gig/QUICKSTART.md
- docs/gig/REKORDBOX_OVERLAY.md

### E. Audit docs
- docs/audit/README.md
- docs/audit/DJ_WORKFLOW_AUDIT.md
- docs/audit/DJ_WORKFLOW_ARCHITECTURE_MAP.md
- docs/audit/DJ_WORKFLOW_BRITTLENESS.md  (try AUDIT_DJ_WORKFLOW_BRITTLENESS.md)
- docs/audit/DJ_WORKFLOW_GAP_TABLE.md
- docs/audit/DJ_WORKFLOW_TRACE.md
- docs/audit/DJ_PIPELINE_DOC_TRIAGE.md
- docs/audit/MISSING_TESTS.md
- docs/audit/REKORDBOX_XML_INTEGRATION.md
- docs/audit/V3_IDENTITY_HARDENING_PLAN.md
- docs/audit/DATA_MODEL_RECOMMENDATION.md
- docs/audit/2026-03-16_v3_identity_hardening_etat_des_lieux.md
- docs/audit/TOOLS_GET_DJ_RUNTIME_TRACE_2026-03-15.md
- docs/testing/V3_IDENTITY_HARDENING.md
- docs/reference/README.md

### F. Prompt files (read all — determine which are complete vs still actionable)
Read every file in .github/prompts/. For each, note:
- Is the task it describes already complete on dev?
- If not, what does it need before it can run?

### G. Source code surface (read, do not modify)
- tagslut/cli/main.py                     (command groups registered)
- tagslut/cli/commands/dj.py              (dj subcommands)
- tagslut/cli/commands/mp3.py             (mp3 subcommands)
- tagslut/cli/commands/lexicon.py         (lexicon subcommands)
- tagslut/cli/commands/master.py          (master subcommands)
- tagslut/storage/v3/schema.py            (track_identity DDL, columns, triggers)
- tagslut/storage/v3/identity_service.py  (identity resolution logic)
- tagslut/exec/mp3_build.py               (mp3 reconcile-scan impl)
- tagslut/exec/master_scan.py             (master scan impl)
- tagslut/exec/lexicon_import.py          (lexicon import impl)
- tagslut/exec/dj_pool_wizard.py          (pool-wizard impl)
- tagslut/exec/transcoder.py              (ffmpeg transcode + validation)
- tagslut/dj/admission.py                 (admit / backfill logic)
- tagslut/dj/xml_emit.py                  (xml emit + validation gate)
- tagslut/metadata/beatport.py            (Beatport provider, token precedence)
- tools/get-intake                        (intake pipeline shell script)
- tools/get                               (intake entrypoint)
- Makefile                                (make targets)
- pyproject.toml                          (deps, test config)

### H. DB state (read-only queries — do not write)
Run these sqlite3 queries against the FRESH DB only:
  DB=/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db

Do NOT query:
  /Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db  (LEGACY — read-only archaeology)
  /Users/georgeskhawam/Projects/tagslut_db/music_v3.db  (DELETED symlink — must not exist)
  artifacts/db/*.db  (pre-migration backups — do not query)

  sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
  sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name;"
  sqlite3 "$DB" "SELECT name FROM sqlite_master WHERE type='trigger' ORDER BY name;"
  sqlite3 "$DB" "PRAGMA table_info(track_identity);"
  sqlite3 "$DB" "PRAGMA table_info(mp3_asset);"
  sqlite3 "$DB" "PRAGMA table_info(asset_file);"
  sqlite3 "$DB" "SELECT ingestion_method, ingestion_confidence, COUNT(*) FROM track_identity GROUP BY 1,2;"
  sqlite3 "$DB" "SELECT COUNT(*) FROM asset_file;"
  sqlite3 "$DB" "SELECT COUNT(*) FROM mp3_asset;"
  sqlite3 "$DB" "SELECT COUNT(*) FROM dj_playlist;"
  sqlite3 "$DB" "SELECT COUNT(*) FROM reconcile_log;"
  sqlite3 "$DB" "SELECT migrations_applied FROM migrations_log ORDER BY applied_at DESC LIMIT 5;" 2>/dev/null || sqlite3 "$DB" "SELECT * FROM migrations_applied ORDER BY rowid DESC LIMIT 5;" 2>/dev/null || echo "no migrations table found"

  # Verify symlink trap is gone
  ls -la /Users/georgeskhawam/Projects/tagslut_db/music_v3.db 2>&1

### I. Git state
  cd /Users/georgeskhawam/Projects/tagslut
  git log --oneline -20
  git status --short
  git stash list

### J. Test coverage snapshot
  poetry run pytest tests/ --co -q 2>&1 | tail -5   # count only, no execution
  # Note any test files that import non-existent modules or fail collection

---

## PART 2 — Synthesise and write docs/ACTION_PLAN.md

After reading everything above, write a single file: docs/ACTION_PLAN.md

The file must contain exactly these sections:

### 1. DB state summary
Current row counts, migration level, confirmed FRESH DB path, confirmed symlink status.

### 2. Prompt file audit
For every file in .github/prompts/:
  | prompt file | status | blocker / notes |
One row per file. Status values: COMPLETE | READY | NEEDS_DESIGN | BLOCKED | STALE.
STALE = the task it describes is superseded or already done but the file was not
  marked complete. STALE prompts should be archived, not run.

### 3. Open work — ranked by execution order
Every open item from ROADMAP.md, REDESIGN_TRACKER.md open streams, audit docs,
and anything discovered during source read. Format:

  ## <N>. <title>
  **Status**: UNBLOCKED | BLOCKED | OPERATOR-ONLY | NEEDS-DESIGN
  **Agent**: Codex | Claude Code | Operator
  **Prompt**: <path if exists, else "needs authoring">
  **Depends on**: <item numbers, or "nothing">
  **Done when**: <one observable condition>
  **Notes**: <anything a future agent needs to know — schema gotchas, path traps, etc.>

### 4. Items confirmed complete — do not reopen
Bullet list. One line each. Cite the commit where known.

### 5. Operator-only checklist
Actions that must never be delegated. Short, imperative.

### 6. DB path safety rules (permanent)
Canonical path for FRESH DB. Explicitly state that the symlink at
tagslut_db/music_v3.db is gone and must never be recreated. Any agent that
sees a --db argument pointing at a path without FRESH_2026 in it must stop
and verify before proceeding.

### 7. Known Codex failure patterns observed in this repo
Patterns where Codex has produced bugs before. Each entry: what went wrong,
what the correct behaviour is, what to check in review.

---

## Constraints

- Read-only. No code changes, no schema changes, no git commits.
- Do not run the full test suite. `--co -q` (collect only) is permitted.
- Do not write to any DB file.
- Do not follow or recreate the symlink at tagslut_db/music_v3.db.
- If a file in the read list does not exist, skip it and note "not found" in the plan.
- The output file is docs/ACTION_PLAN.md — one file, no other writes.
- After writing docs/ACTION_PLAN.md, print its line count and first 20 lines.
  Then stop. Do not commit.
