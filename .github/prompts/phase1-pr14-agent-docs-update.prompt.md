You are a technical writer working in the tagslut repository.

Goal:
Update AGENT.md and .codex/CODEX_AGENT.md to accurately reflect the current
v3 state of the project. Both files are significantly stale. Make the smallest
accurate patch that removes obsolete content and adds what is missing.
Do not touch any code, tests, migrations, or other files.

Read first (in order):
1. AGENT.md
2. .codex/CODEX_AGENT.md
3. docs/PROJECT_DIRECTIVES.md
4. docs/PHASE1_STATUS.md
5. docs/ROADMAP.md
6. docs/SURFACE_POLICY.md
7. docs/CREDENTIAL_MANAGEMENT.md

Verify before editing:
- Run: poetry run tagslut --help
- Run: poetry run tagslut auth --help
- Run: poetry run tagslut dj --help
- Note the exact command groups exposed. Do not invent commands not present.

Constraints:
- Modify only AGENT.md and .codex/CODEX_AGENT.md.
- Do not modify .claude/AGENT.md (it correctly defers to /AGENT.md).
- Smallest accurate patch only — do not rewrite sections that are still correct.
- Do not add prose narrative. Use imperative bullet style matching the existing
  voice of each file.
- Do not copy content between files. Each file has a distinct audience:
  AGENT.md is short operator-facing guidance; CODEX_AGENT.md is longer
  Codex-facing implementation context.

Required changes to AGENT.md:
1. Update the "Execution" section: canonical command is `poetry run tagslut`
   (already correct). Add one line: "The `dedupe` alias has been removed."
2. Replace the "Constraints" section with:
   - Do not scan the entire repository.
   - Do not modify artifacts, databases, or external volumes.
   - Do not modify DB files directly — use migrations only.
   - Do not write to $MASTER_LIBRARY, $DJ_LIBRARY, or any mounted volume.
   - Return minimal patches only.

Required changes to .codex/CODEX_AGENT.md:
1. Update "## Canonical command" to add:
   "The `dedupe` alias has been removed. Do not reference it."

2. Replace the entire "### Storage" subsection with:

   ### Storage
   The project uses the v3 identity model with SQLite via the v3 migration runner.

   Active migration chain (applied in this order):
   - 0006: track_identity phase 1 (provider columns, merged_into_id, indexes)
   - 0007: phase 1 column renames
   - 0009: chromaprint fingerprint support
   - 0010: provider uniqueness — beatport, tidal, qobuz, spotify (partial indexes)
   - 0011: provider uniqueness hardening — apple_music, deezer, traxsource
   - 0012: ingestion provenance — ingested_at, ingestion_method, ingestion_source,
           ingestion_confidence (all NOT NULL, five-tier CHECK constraint)

   track_identity provenance fields are NOT NULL. Every insert must supply:
     ingested_at        ISO 8601 UTC, set once, never updated
     ingestion_method   controlled vocabulary — see docs/INGESTION_PROVENANCE.md
     ingestion_source   specific evidence string
     ingestion_confidence  verified | corroborated | high | uncertain | legacy

   Do not touch tagslut/storage/v3/schema.py without a migration file.

   Fresh DB path:  /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db
   Legacy DB path: /Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db
     (legacy is read-only archaeology — do not write to it)

3. Replace the entire "### DJ pipeline" subsection with:

   ### DJ pipeline
   Canonical path:

     FLAC (MASTER_LIBRARY)
       → tagslut intake process-root --phases identify,enrich,art,promote,dj
       → tagslut dj pool-wizard
       → tagslut dj xml emit → Rekordbox XML

   Use only v3-safe phases on a v3 DB: identify, enrich, art, promote, dj.
   Do not use legacy scan phases (register, integrity, hash) on a v3 DB.

   Key DJ commands:
     tagslut dj pool-wizard   Build final MP3 DJ pool from MASTER_LIBRARY
     tagslut dj backfill      Auto-admit all verified MP3s
     tagslut dj validate      Verify DJ library state
     tagslut dj xml emit      Generate Rekordbox XML

   DJ candidate export (read-only, produces CSV):
     make dj-candidates V3=<db> OUT=<csv>
     Implemented in scripts/dj/export_candidates_v3.py

4. Add a new section after "### DJ pipeline":

   ### Credentials
   Token storage: ~/.config/tagslut/tokens.json (single source of truth).
   tokens.json takes precedence over env vars. Env var fallback logs a warning.

   CLI:
     tagslut auth token-get <provider>   Print access token for shell capture
     tagslut auth status                 Show auth status for all providers

   Shell scripts must use:
     TOKEN=$(tagslut auth token-get beatport 2>/dev/null)
   Not: source env_exports.sh (removed from harvest scripts).

   Full credential model: docs/CREDENTIAL_MANAGEMENT.md

5. Update "## Working rules" — add these two rules:
   - Do not use `git push --force` or `git filter-repo` — operator-only procedures.
   - Do not run the full test suite during implementation. Targeted pytest only:
     `poetry run pytest tests/<specific_module> -v`
     Full suite (`poetry run pytest tests/ -x -q`) is permitted only as a final
     gate immediately before merging a PR, and only when the prompt says so explicitly.

Done when:
- AGENT.md and .codex/CODEX_AGENT.md reflect the actual current state.
- No obsolete migration version numbers or stale pipeline descriptions remain.
- .claude/AGENT.md is untouched.
- No code, tests, migrations, or other files are modified.
- `poetry run tagslut --help` still exits 0 (no accidental breakage).
- Conventional commit: docs(agent): update AGENT.md and CODEX_AGENT.md for v3 Phase 1 completion
