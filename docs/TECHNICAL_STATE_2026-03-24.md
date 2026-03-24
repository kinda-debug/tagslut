# tagslut Technical State Report — 2026-03-24

Engineering reference documenting current repository state, migration chain, schema enforcement, and active workstreams.

---

## Migration Chain Status

**FRESH DB**: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`

```
Migrations: 1-14 (complete, continuous, no gaps)
Schema version: V3_SCHEMA_VERSION = 14
Last migration: 0014_dj_validation_state (2026-03-23)
```

**Applied migrations**:
1. Initial v3 schema
2. Identity merge support
3. Preferred asset support
4. Identity lifecycle status
5. DJ profile support
6. Phase 1 canonical identity extension
7. Rename phase 1 columns to canonical
8. Asset analysis + DJ export metadata views
9. Chromaprint columns + indexes
10. Track identity provider uniqueness
11. Provider uniqueness hardening
12. Ingestion provenance (columns + trigger)
13. Five-tier confidence CHECK constraints (2026-03-23)
14. DJ validation state table

**Legacy DB**: `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db`
- Status: Read-only archaeology
- Reason: Built on MusicBrainz Picard tags (unverifiable origin)
- Usage: `--db LEGACY_PATH` for reference only

---

## Schema Enforcement State

**track_identity CHECK constraints** (enforced via migration 0013):

```sql
ingestion_confidence CHECK (
    ingestion_confidence IN (
        'verified',      -- Two+ providers confirmed same ISRC at ingest
        'corroborated',  -- Multiple stored provider IDs agree on ISRC
        'high',          -- Single provider API match with confirmed ID
        'uncertain',     -- Fuzzy match, fingerprint <0.90, or conflict
        'legacy'         -- Picard tag, unknown origin, unverified migration
    )
)

ingestion_method CHECK (
    ingestion_method IN (
        'provider_api',              -- Direct API match
        'isrc_lookup',               -- ISRC-only resolution
        'fingerprint_match',         -- Chromaprint/AcoustID
        'fuzzy_text_match',          -- Artist/title fuzzy
        'picard_tag',                -- MusicBrainz Picard (legacy)
        'manual',                    -- Operator-entered
        'migration',                 -- Imported from prior schema
        'multi_provider_reconcile'   -- Reconciled across multiple IDs
    )
)
```

**Provenance trigger** (enforced via migration 0012):
- `trg_track_identity_provenance_required` — BEFORE INSERT
- Rejects NULL or empty: `ingested_at`, `ingestion_method`, `ingestion_source`, `ingestion_confidence`

**Provider uniqueness** (enforced via migrations 0010-0011):
- Partial unique indexes on all provider IDs (beatport_id, tidal_id, spotify_id, etc.)
- Active identities only (`WHERE merged_into_id IS NULL`)
- Non-empty strings only (`WHERE TRIM(provider_id) != ''`)

---

## Current DB State (FRESH)

**Row counts** (2026-03-24):
```
track_identity:      188 rows (all with valid provenance)
asset_file:       25,534 rows
mp3_asset:            1 row
dj_admission:         0 rows (empty, ready for backfill)
dj_validation_state:  0 rows (table exists, ready for validation runs)
identity_status:    188 active
preferred_asset:    188 rows
```

**Confidence tier distribution**:
```
high: 188 rows (all current identities are single-provider API matches)
```

**Provenance completeness**: 100% (all 188 rows have complete provenance)

**CHECK constraint enforcement**: Verified working
- Invalid confidence tier → rejected at insert
- Invalid ingestion method → rejected at insert
- `multi_provider_reconcile` + `corroborated` → accepted

---

## Volume Layout

**Current machine**:
```
/Volumes/MUSIC/MASTER_LIBRARY       — FLAC master library (source of truth)
/Volumes/MUSIC/MP3_LIBRARY          — Full-tag MP3 copies (playback)
/Volumes/MUSIC/DJ_LIBRARY           — DJ-admitted MP3s (admission-gated)
/Volumes/MUSIC/DJ_POOL_MANUAL_MP3   — Manual DJ pool additions
/Volumes/MUSIC/mdl                  — Staging root for downloads
/Volumes/MUSIC/lexicondj.db         — Lexicon DJ database (read-only reference)
/Volumes/SAD/                       — Legacy epoch DBs (read-only, no writes)
```

**Environment variables**:
```
MASTER_LIBRARY = /Volumes/MUSIC/MASTER_LIBRARY
DJ_LIBRARY     = /Volumes/MUSIC/DJ_LIBRARY
DJ_MP3_ROOT    = /Volumes/MUSIC/DJ_LIBRARY
STAGING_ROOT   = /Volumes/MUSIC/mdl
```

**Unmounted volume failure policy**: Operations requiring unmounted volumes must fail with clear error, not silently fall back to local paths.

---

## Download Strategy (Critical — Never Violate)

**Primary audio source**: TIDAL (via tiddl)
**Metadata authority**: Beatport

**Workflow**:
1. User provides URL → Extract ISRC
2. Download from TIDAL (tiddl)
3. Enrich with Beatport metadata (BPM, key, genre, catalog numbers)

**Tool roles**:
- `tiddl`: PRIMARY audio downloads (always)
- `beatportdl`: Token provider for Beatport API access (metadata only, NEVER downloads)
- Beatport API: Metadata enrichment
- tagslut: Workflow orchestration, DB management

**Edge cases**:
- Beatport link + no TIDAL match → Flag for manual review, do NOT auto-download from Beatport
- TIDAL link → Download directly, attempt Beatport enrichment via ISRC lookup
- ISRC conflict → Trust TIDAL ISRC (audio source), log discrepancy

---

## Canonical DJ Workflow

**4-stage pipeline** (all operator docs aligned 2026-03-23):

```
Stage 1: tagslut intake
  → Ingest FLAC to MASTER_LIBRARY
  → Dual-write to asset_file + track_identity
  → Trigger: post_move_enrich_art.py background enrichment

Stage 2: tagslut mp3 build|reconcile
  → Transcode FLAC → MP3 (full tags, archive quality)
  → Populate mp3_asset table
  → FFmpeg output validation (existence, size, mutagen, duration >1s)

Stage 3: tagslut dj backfill
  → Copy admitted MP3s to DJ_LIBRARY
  → Populate dj_admission table
  → Admission criteria: identity_status='active', preferred_asset exists

Stage 4: tagslut dj validate → dj xml emit|patch
  → Pre-emit gate: dj validate creates dj_validation_state row
  → XML emit blocked unless state_hash matches last validation pass
  → TrackID stability: dj_track_id_map prevents reassignment
  → Patch mode: Rekordbox XML manipulation for metadata-only updates
```

**Legacy wrapper status**:
- `tools/get --dj` → DEPRECATED (warning shown)
- `tools/get-intake --dj` → DEPRECATED (warning shown)
- Canonical path: 4-stage pipeline via `tagslut` CLI only

---

## Ingestion Provenance Policy

**Spec**: `docs/INGESTION_PROVENANCE.md` + `docs/MULTI_PROVIDER_ID_POLICY.md`

**Two ingestion tracks**:

**Track A (clean-slate)**: Files from Beatport/TIDAL via `tools/get --enrich`
- `ingestion_method = 'provider_api'`
- `ingestion_confidence = 'verified'` (both providers agree) or `'high'` (one provider)
- Provider ID stored at download time

**Track B (legacy)**: Older files with accumulated cross-provider IDs
- `ingestion_method = 'multi_provider_reconcile'`
- `ingestion_confidence`:
  - `'corroborated'` if all IDs agree on ISRC
  - `'uncertain'` if conflict detected
- Conflicts preserved in `canonical_payload_json.provider_id_conflicts` (never dropped)

**Provider ID policy**:
- All provider IDs preserved if they don't conflict with ISRC
- Agreement across providers = positive confirmation
- Conflict = provenance failure (flagged, not silently resolved)

---

## Credential Management Status

**Current state** (as of 2026-03-22):
- Primary: `TokenManager` + `~/.config/tagslut/tokens.json`
- Legacy: `env_exports.sh` (archived, still referenced by 3 harvest scripts)
- Postman: Environment vars (integration testing only)

**Precedence fix** (commit 249ac8d):
- `beatport.py` now checks tokens.json FIRST
- Env var fallback with warning log
- `tagslut auth token-get <provider>` CLI for shell scripts

**Remaining work**:
- Migrate 3 harvest scripts to use `tagslut token-get`
- Research Beatport token refresh support
- Decision needed on env var fallback removal

---

## Test Coverage

**Migration 0013** (10 tests passing):
- `tests/storage/v3/test_migration_0013.py` — Pre/post vocab enforcement
- `tests/storage/v3/test_migration_runner_v3.py` — Upgrade path 12→13→14

**DJ pipeline** (E2E proofs):
- `tests/e2e/test_dj_pipeline.py`:
  - E2E-3: Backfill + validate + emit populate dj_track_id_map
  - E2E-4: Logical XML identity, stable TrackIDs, manifest hashes
  - E2E-5: Patch manifest persistence, tamper detection

**Total suite** (as of last run):
- 579 passed, 2 failed (legacy, not blocking)

---

## Active Workstreams

**Completed (2026-03-23)**:
1. ✅ Migration 0013 (five-tier confidence CHECK)
2. ✅ Migration 0014 (dj_validation_state table)
3. ✅ DJ pipeline contract alignment (docs synchronized)
4. ✅ Intake pipeline hardening (pre-existing on dev)
5. ✅ Repo cleanup (CLEANUP_MANIFEST.md)

**Blocked/Paused**:
- Lexicon reconcile (36% unmatched, 11,679 identities)
- DJ admission backfill (empty DB, pipeline-state-dependent)

**Ready to proceed**:
- DJ pipeline hardening (§3 in ROADMAP.md)
- Phase 2 seam work
- Credential consolidation Phase 2

---

## File Locations Reference

**Core schema**:
- `tagslut/storage/v3/schema.py` — Fresh schema creation
- `tagslut/storage/v3/migrations/*.py` — Migration files
- `supabase/migrations/*.sql` — Postgres migrations

**Documentation**:
- `docs/DB_V3_SCHEMA.md` — Schema reference
- `docs/INGESTION_PROVENANCE.md` — Provenance spec
- `docs/MULTI_PROVIDER_ID_POLICY.md` — Five-tier confidence model
- `docs/DJ_PIPELINE.md` — 4-stage workflow
- `docs/ROADMAP.md` — Task assignments
- `docs/PROGRESS_REPORT.md` — Session history
- `docs/ACTION_PLAN.md` — Dependency-ordered execution

**Test fixtures**:
- `tests/conftest.py` — PROV_DEFAULTS, PROV_COLS, PROV_VALS

**Prompts** (for agent execution):
- `.github/prompts/*.prompt.md` — Codex/Claude Code execution specs
- `docs/PROMPT_SUITE_COMPLETE.md` — Rate-limit safe migration guide

---

## Known Issues (Active)

**None** — Migration chain complete, schema enforced, DJ pipeline documented.

---

## Verification Commands

**Check migration state**:
```bash
cd /Users/georgeskhawam/Projects/tagslut
python3 << 'EOF'
import sqlite3
conn = sqlite3.connect("/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db")
cursor = conn.cursor()
versions = [v[0] for v in cursor.execute(
    "SELECT version FROM schema_migrations WHERE schema_name='v3' ORDER BY version"
).fetchall()]
print(f"Applied migrations: {versions}")
expected = list(range(1, 15))
missing = [v for v in expected if v not in versions]
print(f"Status: {'✅ Complete 1-14' if not missing else f'❌ Missing {missing}'}")
conn.close()
EOF
```

**Test CHECK constraints**:
```bash
poetry run pytest tests/storage/v3/test_migration_0013.py \
                 tests/storage/v3/test_migration_runner_v3.py -q
```

**Check DB row counts**:
```bash
sqlite3 /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db << 'SQL'
SELECT 'track_identity', COUNT(*) FROM track_identity
UNION ALL SELECT 'asset_file', COUNT(*) FROM asset_file
UNION ALL SELECT 'mp3_asset', COUNT(*) FROM mp3_asset
UNION ALL SELECT 'dj_validation_state', COUNT(*) FROM dj_validation_state;
SQL
```

---

## Root Cause Resolutions (Historical)

**Migration 0013 gap** (resolved 2026-03-23):
- **Problem**: Migration 0012 added provenance columns but NOT CHECK constraints
- **Documentation claimed**: "Migration 0013 included in 0012" (false)
- **Reality**: Five-tier model documented but never enforced
- **Resolution**: Created explicit migration 0013 with table recreation + CHECK constraints
- **Lesson**: Schema enforcement must be implemented when columns are added, not deferred

**Intake pipeline dual_write** (resolved 2026-03-22):
- **Problem**: `dual_write = false` by default, v3 tables never populated
- **Resolution**: Created `~/.config/tagslut/config.toml` with `dual_write = true`
- **One-time backfill**: 174 files from MASTER_LIBRARY → v3 schema

---

**End of Technical State Report**
