# TAGSLUT PROJECT: SUPERMASSIVE SYNTHESIS REPORT
## Strategic Architecture + Tactical Evidence + Work Decomposition

**Report Date:** March 15, 2026
**Sources:** ChatGPT strategic analysis + PERPLEXITYREPORT + AGENT.md + CHANGELOG.md + PROGRESS_REPORT.md + 6 audit documents + handoff bundle  .codex/AGENT.md
**Scope:** Full repo state, architectural constraints, tactical blockers, work priorities, risk matrix, Claude Code operating rules

---

# PART 1: STRATEGIC OVERVIEW (Foundation)

## 1.0 Executive Summary

The tagslut project has **transitioned from ambiguous "DJ mode" behavior to an explicit 4-stage pipeline architecture.** The right architecture is now documented and partially implemented. The remaining work is verification and completion.

### What Changed

**Old Model (Broken in Practice)**
- `tools/get --dj` was a vague "do something smart" command
- DJ state was smeared across file columns, path-matching logic, and transient wrapper state
- Two hidden code paths: promotion-fed vs precheck-hit fallback
- Operator experience collapsed into manual file handling
- No clean separation: master FLAC ≠ MP3 library ≠ DJ library

**New Model (Documented, Partially Implemented)**
- Four explicit stages: MP3 registration/build → DJ admission → validation → Rekordbox XML emit/patch
- Separate tables: `mp3_asset` (derivative truth), `dj_admission` (curation truth), `dj_track_id_map` (stable TrackIDs)
- Single source of truth per layer: FLAC master → identity → MP3 asset → DJ admission → XML projection
- Canonical commands: `tagslut mp3 reconcile`, `tagslut dj backfill`, `tagslut dj validate`, `tagslut dj xml emit`

### Current Status (2026-03-14)

✅ **Completed**
- Schema migration 0010 applied (7 DJ tables live)
- Lexicon metadata backfill executed (20,517 identities enriched, 29,442 reconcile_log rows)
- AGENT.md canonical config written
- 6 audit documents produced (DJ_WORKFLOW_AUDIT.md, GAP_TABLE.md, etc.)
- 4 prompt files defining work orders (hardening, Lexicon reconcile, post-0010 narrative, etc.)

⚠️ **In-Flight**
- Phase 1 stacked PRs (#193, #185, #186) on dev branch
- CLI help text parity not yet verified
- Retroactive MP3 admission tests not yet written
- Rekordbox XML determinism under patch cycles unproven

❌ **Not Yet Started**
- Enforce `tools/get --dj` deprecation (code still has two paths)
- Reconcile existing DJ/MP3 library against TAGSLUT_DB (Lexicon reconcile prompt)
- Validate import layering (tagslutcore → tagslutdj order)
- Full end-to-end test suite for 4-stage pipeline

### The Right Stance for Claude Code

**Trust documents for intended contract. Verify code against promises. Fix misalignment.**

- ✅ Trust AGENT.md for repo doctrine
- ✅ Trust CHANGELOG.md claims provisionally, verify against code
- ✅ Trust audit docs for problem diagnosis
- ❌ Do NOT trust shell wrappers to implement the documented 4-stage contract
- ❌ Do NOT assume enrichment timing is consistent across DJ vs normal intake
- ❌ Do NOT reuse the `tools/get --dj` pattern for other features

---

## 2.0 Source Hierarchy (Strategic Framework from ChatGPT Report)

**Read and trust in this order:**

### Tier 1: Canonical Truth

**AGENT.md** — Vendor-neutral instruction file. Defines:
- Repo purpose (identity-based music library operations)
- Canonical CLI surface (intake, index, decide, execute, verify, report, auth, dj, mp3, gig, export)
- Core invariants (FLAC is canonical, identity lives in DB not paths, DJ outputs are downstream)
- Storage ownership (asset_file, track_identity, asset_link, preferred_asset, identity_status)
- Git hygiene (no force-push, explicit staging, branch truth gates, worktree recovery)
- 4-stage DJ pipeline with explicit commands
- Migration verification checklist

**→ Read AGENT.md first. It is the source of truth for repo doctrine.**

### Tier 2: Tool-Specific Overrides

**CLAUDE.md and/or .codex/AGENT.md and/or .codex/AGENT.md** — Behavioral constraints for Claude-family tools:
- Minimal reversible changes
- Docs before code when they diverge
- No destructive git operations (no force-push, no rebase, no history rewriting)
- Explicit comparison of intended vs actual behavior
- Guardrails: move-only semantics, zone-based file management, audit prompts

**→ Read CLAUDE.md and/or .codex/AGENT.md for procedural rules, not architecture.**

### Tier 3: Operator Model

**README.md** — Clearest public explanation:
- v3 database-first model
- Primary downloader flow (`tools/get`)
- **Legacy status of `tools/get --dj`** with explicit deprecation
- **Canonical 4-stage DJ pipeline** with named stages and example commands
- Move plan execution
- Phase 1 stack synchronization

**→ Read README.md for what operators see. Ensure CLI help matches it.**

### Tier 4: Recent Changes

**CHANGELOG.md** — Claims the 4-stage pipeline is real:
- Added: `tagslut mp3 build`, `tagslut mp3 reconcile` (Stage 1)
- Added: `tagslut dj admit`, `tagslut dj backfill`, `tagslut dj validate` (Stage 2)
- Added: `tagslut dj xml emit`, `tagslut dj xml patch` (Stage 3)
- Added: 6 DJ/MP3 tables in migration 0010 (mp3_asset, dj_admission, dj_track_id_map, dj_playlist, dj_playlist_track, dj_export_state)
- Added: 28 E2E tests covering determinism, manifest integrity, stable TrackIDs
- Changed: `tools/get --dj` demoted to legacy with deprecation warning

**→ Treat CHANGELOG claims as testable assertions. Verify code against them.**

### Tier 5: Strategic Context

**PROGRESS_REPORT.md** — Current execution state (2026-03-14):
- Schema migration 0010 applied
- Lexicon backfill completed (20,517 identities)
- Phase 1 stack in flight
- Known risks: compatibility wrappers, provider metadata gaps, unfinished stacked branches

**→ Use for current state snapshot. Cross-check against branch activity.**

### Tier 6: Diagnosis

**docs/audit/DJ_WORKFLOW_AUDIT.md** — Hostile audit of the *failure mode*:
- Why `--dj` is unreliable (promotion-dependent, precheck-hit fallback, no durable MP3 registry)
- Why DJ workflow collapsed (two hidden paths, fragmented enrichment, operator surprise)
- Root causes: design flaws, misleading command contracts, broken data contracts

**→ Read for problem diagnosis. Use to validate fixes.**

### Tier 7: Work Orders

**Prompt files** (.github/prompts/) — High-signal implementation tasks:
- `dj-pipeline-hardening.prompt.md` — Enforce 4-stage pipeline (Tasks 1–5: triage docs, make workflow undeniable, demote legacy paths, harden invariants, write E2E tests)
- `dj-workflow-audit.prompt.md` — Audit request template (use for repeatable future audits)
- `lexicon-reconcile.prompt.md` — Real-world MP3/DJ library reconciliation (dry-run, resumable, reconcile_log)
- `open-streams-post-0010.prompt.md` — Write a blog post explaining the new model

**→ Use as concrete task lists. Execute in order after verification.**

---

## 3.0 Verified Repo Doctrine (Coherent Architecture)

### 3.1 Master FLAC Library Is Canonical

**Evidence:**
- AGENT.md: "FLAC master library is always the source of truth"
- README.md: "Master library is the source of truth"
- DB_V3_SCHEMA.md: `asset_file`, `track_identity`, `asset_link` define ownership
- PROGRESS_REPORT.md: Lexicon backfill targets `track_identity` (not `mp3_asset` or `dj_admission`)

**What this means:**
- All identity truth lives in `track_identity` table
- All physical file truth lives in `asset_file` table
- Moves are auditable via `provenance_event` table
- DJ outputs depend on master state, never vice versa

**Constraint for Claude Code:**
- ✅ DO write DJ changes to dj_* tables
- ✅ DO link DJ state to track_identity via identity_id
- ❌ DON'T mutate track_identity or asset_file to achieve DJ outcomes
- ❌ DON'T make master library state depend on DJ export success

---

### 3.2 Identity Truth Lives in Database, Not Paths

**Evidence:**
- AGENT.md: "Identity truth lives in `track_identity`, not in file paths"
- AGENT.md: "If physical state and identity state disagree, trust the owner table for that fact category"
- DJ_WORKFLOW_AUDIT.md: "DJ state is smeared across `files` columns, ad hoc export code, and fallback linker logic instead of explicit DJ entities"

**What this means:**
- Canonical identity keys: ISRC, beatport_id, tidal_id, spotify_id, musicbrainz_id, identity_key
- File paths are transient facts, not identity anchors
- Asset-to-identity linking is explicit via `asset_link` table
- Identity merges are recorded in `track_identity.merged_into_id`

**Constraint for Claude Code:**
- ✅ DO use identity_id as the stable reference
- ✅ DO look up identities by ISRC or normalized artist+title
- ❌ DON'T infer identity from file paths
- ❌ DON'T use path-matching as the primary identity linking mechanism

---

### 3.3 DJ Outputs Are Downstream Products

**Evidence:**
- AGENT.md: "DJ pools, MP3 exports, playlists, and review artifacts are downstream products"
- DJ_WORKFLOW_AUDIT.md: "The filesystem stores audio; the database stores meaning"
- DATA_MODEL_RECOMMENDATION.md: "Keep one canonical SQLite database, but split the model into explicit master, MP3, and DJ layers"

**What this means:**
- MP3 library (`mp3_asset`) is a managed derivative of FLAC masters
- DJ library (`dj_admission`) is a curated subset of MP3s
- Rekordbox XML is a deterministic projection from `dj_*` tables
- Rebuilding any downstream layer should not corrupt upstream truth

**Constraint for Claude Code:**
- ✅ DO treat MP3 generation as an explicit operation (mp3 build, mp3 reconcile)
- ✅ DO track MP3 state in mp3_asset, not as a side effect
- ❌ DON'T make master library operations depend on MP3 pool success
- ❌ DON'T treat Rekordbox XML as a source of identity truth

---

### 3.4 Planning and Execution Stay Separate

**Evidence:**
- AGENT.md: "Prefer `decide -> execute -> verify` for all major operations"
- README.md: "Execution writes receipts into v3 move/provenance tables"
- DJ_WORKFLOW_AUDIT.md: "Compares docs/promises against implementation reality"

**What this means:**
- Plans are stored in DB (move_plan, dj_export_state) before execution
- Execution is auditable (move_execution, provenance_event)
- Dry-run is always available before --execute
- Plans can be reviewed, rejected, or re-run without side effects

**Constraint for Claude Code:**
- ✅ DO use --dry-run by default on all destructive operations
- ✅ DO write plan state to DB before execution
- ✅ DO verify against prior state before mutating (manifest hashes, checksums)
- ❌ DON'T execute without explicit user confirmation (--execute flag)
- ❌ DON'T skip validation / verification steps

---

## 4.0 What Actually Failed in Practice (The Diagnosis)

### The Failure Mode

**From DJ_WORKFLOW_AUDIT.md:**

The old `tools/get --dj` workflow failed because:

1. **No Durable MP3 Abstraction**
   - MP3 generation was tied to same-run FLAC promotion (`PROMOTED_FLACS_FILE`)
   - If no FLACs were promoted, MP3s were silently skipped
   - No way to reproducibly build/reconcile MP3s from canonical masters
   - Evidence: DJ_WORKFLOW_TRACE.md maps two divergent paths with exact code locations

2. **Hidden Branching in Operator Surface**
   - Same command (`tools/get --dj`) produced different outcomes based on precheck decision (inventory already exists?)
   - Precheck-hit invoked alternate path: `link_precheck_inventory_to_dj` + `precheck_inventory_dj.py`
   - Operator never knew which path was executing
   - Evidence: DJ_WORKFLOW_AUDIT.md sections 2–4, DJ_WORKFLOW_TRACE.md path trace

3. **DJ State Smeared Across Multiple Layers**
   - DJ metadata lived in `files.dj_pool_path`, `files.rekordbox_id`, `files.dj_set_role` columns
   - No separate DJ admission contract
   - No dedicated MP3 asset registry
   - Path-matching and tag-matching drove admission instead of explicit linking
   - Evidence: DJ_WORKFLOW_AUDIT.md sections 3, 6; DATA_MODEL_RECOMMENDATION.md

4. **Enrichment Timing Inconsistency**
   - `tools/get --dj` suppressed normal background enrichment (enrich/art)
   - DJ-facing MP3s diverged from canonical enrichment state
   - Metadata completeness depended on which code path executed
   - Evidence: DJ_WORKFLOW_AUDIT.md section 7

5. **Rekordbox Integration as Afterthought**
   - XML export was a utility, not a stable output contract
   - TrackID stability was unproven
   - No deterministic projection from DB state
   - No safeguards against tampering or rebuilding
   - Evidence: REKORDBOX_XML_INTEGRATION.md decision doc

### Why This Mattered

**From DJ_WORKFLOW_AUDIT.md (Top 5 Reasons):**

1. `--dj` is fed by `PROMOTED_FLACS_FILE`, so DJ output depends on same-run promotion side effects
2. Precheck-hit tracks take a different DJ code path than newly promoted tracks
3. DJ state is smeared across `files` columns, ad hoc export code, and fallback linker logic
4. Enrichment timing changes when `--dj` is passed
5. Rekordbox handling exists as utilities, not a formal deterministic export contract

**Operator Impact:**
- Download a track that already exists → precheck-hit path → get transient DJ copies
- Download a new track → promotion path → get durable DJ copies
- **Same operator action, different outcomes, no way to tell which code path is running**
- Result: confusion, manual file handling, loss of trust in automation

---

## 5.0 The Current Intended Model (Four Explicit Layers)

### Layer 1: Master FLAC Library (Canonical)

**Source of Truth for:**
- Recording identity (track_identity)
- Enrichment state (canonical_title, canonical_artist, canonical_bpm, canonical_key, etc.)
- Preferred asset selection (preferred_asset per identity)
- Move history (provenance_event)

**Owned by Tables:**
- `asset_file` — physical file facts (path, checksum, size, duration, integrity)
- `track_identity` — canonical identity facts (ISRC, beatport_id, normalized names, enrichment)
- `asset_link` — binding between asset and identity
- `preferred_asset` — deterministic selection
- `identity_status` — lifecycle (active, orphan, archived)

**Operator Contract:**
- Primary downloader: `tools/get <provider-url>`
- Promotion: `tagslut execute promote-tags`
- Enrichment: `tagslut index enrich`
- Integrity: `tools/review/check_integrity_update_db.py` or `tagslut index duration-check`

**Invariants:**
- FLAC files are authoritative
- Identity truth never depends on DJ state
- Moves are auditable

---

### Layer 2: MP3 Library (Managed Derivative)

**Source of Truth for:**
- Which master FLACs have been transcoded to MP3
- MP3 derivative checksums, paths, bitrates, sample rates
- Which MP3 assets are ready (verified, missing, superseded)
- Linkage back to canonical identity and master FLAC source

**Owned by Tables:**
- `mp3_asset` — transcoded derivative facts
  - `identity_id` — link to track_identity (canonical)
  - `asset_id` — link to source FLAC asset_file
  - `path` — absolute MP3 path
  - `content_sha256`, `size_bytes`, `bitrate`, `sample_rate`, `duration_s`
  - `status` — unverified, verified, missing, superseded
  - `transcoded_at`, `reconciled_at`
- `reconcile_log` — append-only record of every reconciliation decision

**Operator Contract:**
- **Stage 1a (Build):** `tagslut mp3 build --db <DB> --identity-id <id>` — Transcode preferred FLAC for identity to MP3
- **Stage 1b (Reconcile):** `tagslut mp3 reconcile --db <DB> --mp3-root <path>` — Scan existing MP3s, match to identities, register in mp3_asset
- **Dry-run always available:** No files written until `--execute`

**Invariants:**
- One `mp3_asset` row per registered MP3
- Each mp3_asset links to exactly one identity and optionally one master FLAC asset
- Status field reflects verification/readiness
- Reconcile operations are idempotent (re-running produces same results)

**Evidence:**
- CHANGELOG.md claims mp3_build and mp3_reconcile now exist
- DB_V3_SCHEMA.md documents mp3_asset table structure
- DATA_MODEL_RECOMMENDATION.md recommends this separation

---

### Layer 3: DJ Library (Curated Admission)

**Source of Truth for:**
- Which MP3 assets are admitted into the curated DJ library
- DJ-specific metadata: rating, energy, set_role
- Playlist membership and ordering
- Stable Rekordbox TrackID assignments

**Owned by Tables:**
- `dj_admission` — one row per admitted track
  - `identity_id` — link to track_identity (canonical)
  - `mp3_asset_id` — preferred MP3 for this admission
  - `status` — pending, admitted, rejected, needs_review
  - `admitted_at`, `notes`
- `dj_track_id_map` — stable TrackID assignments (UNIQUE per dj_admission, never reassigned)
- `dj_playlist` — playlist hierarchy (name, parent_id)
- `dj_playlist_track` — membership (playlist_id, dj_admission_id, ordinal)
- `dj_track_profile` — identity-layer curation (rating 0–5, energy 0–10, set_role)

**Operator Contract:**
- **Stage 2a (Admit):** `tagslut dj admit --db <DB> --identity-id <id> --mp3-asset-id <id>` — Admit single track
- **Stage 2b (Backfill):** `tagslut dj backfill --db <DB>` — Auto-admit all unadmitted mp3_asset rows with status=ok
- **Stage 2c (Validate):** `tagslut dj validate --db <DB>` — Check missing files, empty metadata, duplicate admissions
- **Dry-run always available**

**Invariants:**
- One `dj_admission` per identity (UNIQUE on identity_id)
- One `dj_track_id_map` per dj_admission (UNIQUE on dj_admission_id)
- TrackID is never reassigned once assigned
- Playlist memberships only reference admitted tracks
- Validation must pass before XML emit

**Evidence:**
- CHANGELOG.md claims dj admit, dj backfill, dj validate added
- DB_V3_SCHEMA.md documents all dj_* tables
- DJ_WORKFLOW.md describes stages 1–3 in detail

---

### Layer 4: Rekordbox XML Projection (Formal Interoperability)

**Source of Truth for:**
- Deterministic Rekordbox XML document
- Manifest hash (SHA-256 of emitted XML)
- Export scope (which playlists, which tracks)
- Patch state (prior export, changes applied)

**Owned by Tables:**
- `dj_export_state` — one row per emit/patch
  - `kind` — rekordbox_xml, nml, m3u, etc.
  - `output_path` — absolute path to emitted file
  - `manifest_hash` — SHA-256 of file contents
  - `scope_json` — filter/scope used for emit
  - `emitted_at`

**Operator Contract:**
- **Stage 3a (Emit):** `tagslut dj xml emit --db <DB> --output <path>` — Emit deterministic XML from dj_* state
  - Assigns stable TrackIDs (persisted in dj_track_id_map)
  - Records manifest hash
  - Runs validation (unless --skip-validation)
  - **Same DB state → identical XML on repeated emits**
- **Stage 3b (Patch):** `tagslut dj xml patch --db <DB> --output <path>` — Patch prior XML after library changes
  - Verifies prior XML file matches stored manifest hash (fails loudly if tampered)
  - Re-emits from updated dj_* state
  - Preserves TrackIDs from dj_track_id_map
  - **Rekordbox cue points survive re-imports**
- **Dry-run for planning, --execute for writing**

**Invariants:**
- TrackIDs in dj_track_id_map are stable and unique
- XML emission is deterministic (same DB → same XML)
- Playlist ordering is stable (ordered by ordinal, then by dj_admission_id)
- Patch verifies prior export state before modifying XML
- Rebuilding from DB produces logically equivalent XML

**Evidence:**
- CHANGELOG.md claims dj xml emit and dj xml patch added with manifest integrity
- REKORDBOX_XML_INTEGRATION.md documents design decisions
- DJ_WORKFLOW.md Stage 4 describes both commands

---

## 6.0 Canonical Workflow (What Operators Execute)

### The 4-Stage DJ Pipeline

**Assume this is the canonical workflow unless code proves otherwise.**

#### Stage 1: Register/Build MP3 Derivatives

**Purpose:** Establish durable MP3 asset state

**Option 1a: Build from Masters**
```bash
tagslut mp3 build --db <DB> --master-root <LIBRARY> --dj-root <MP3_ROOT> --execute
```
- Transcodes preferred FLAC for each identity to <MP3_ROOT>
- Creates mp3_asset rows

**Option 1b: Reconcile Existing MP3s**
```bash
tagslut mp3 reconcile --db <DB> --mp3-root <DJ_LIBRARY> --execute
```
- Scans existing MP3 directory
- Matches to identities via ISRC, then title+artist
- Creates mp3_asset rows (status=verified)
- Logs match decisions to reconcile_log

**Key:** Dry-run is default. No files written until --execute.

#### Stage 2: Admit Tracks to DJ Library

**Purpose:** Select curated subset of MP3s for DJ performance use

**Option 2a: Admit Individual Track**
```bash
tagslut dj admit --db <DB> --identity-id <id> --mp3-asset-id <id> [--notes "..."]
```

**Option 2b: Backfill Auto-Admit**
```bash
tagslut dj backfill --db <DB>
```
- Auto-admits all unadmitted mp3_asset rows with status=ok
- Idempotent (already-admitted tracks skipped)

**Output:** dj_admission rows created, dj_track_id_map populated with stable TrackIDs

#### Stage 3: Validate DJ Library State

**Purpose:** Detect missing files, empty metadata, inconsistencies

```bash
tagslut dj validate --db <DB>
```

**Checks:**
- All referenced MP3 files exist
- dj_admission entries have non-empty title/artist
- dj_track_id_map has stable assigned TrackIDs
- No duplicate admissions for same identity
- No orphaned playlist memberships

**Output:** Validation report with errors/warnings

#### Stage 4: Emit or Patch Rekordbox XML

**Purpose:** Create or update Rekordbox-compatible XML with stable IDs

**Option 4a: Fresh Emit**
```bash
tagslut dj xml emit --db <DB> --output rekordbox.xml
```
- Generates XML from dj_admission + dj_playlist* state
- Assigns TrackIDs sequentially (persisted in dj_track_id_map)
- Records manifest hash in dj_export_state
- Fails if validation errors (unless --skip-validation)
- **Same DB state → identical XML every time**

**Option 4b: Patch After Changes**
```bash
tagslut dj xml patch --db <DB> --output rekordbox_v2.xml --prior-export-id <id>
```
- Loads prior export state from DB
- Verifies on-disk XML file matches stored manifest hash
- Re-emits from updated dj_* state
- Preserves TrackIDs (no reassignment)
- Records updated manifest in dj_export_state
- **Rekordbox cue points survive because TrackIDs are stable**

---

## 7.0 Critical Gaps Between Documented and Implemented

### Gap 1: Two Divergent DJ Paths in `tools/get --dj`

**Evidence:** DJ_WORKFLOW_TRACE.md (full path map), DJ_WORKFLOW_AUDIT.md (sections 2–4)

**Path A: Promotion-Fed (Primary Intake)**
- `tools/get <url> --dj` downloads and promotes FLACs
- MP3 generation feeds from `PROMOTED_FLACS_FILE`
- If empty, silent warning, zero DJ output
- Location: tools/get-intake DJ build block

**Path B: Precheck-Hit Fallback**
- When precheck decides track already exists, skips download/promotion
- Calls `link_precheck_inventory_to_dj` → `precheck_inventory_dj.py`
- Tag-matches, reuses paths, or transcodes from tag snapshot
- **Different behavior, different code, operator invisible**

**Risk:** Same command produces inconsistent outcomes. No single durable MP3 abstraction.

**What to Do:**
- Option 1 (Hard deprecation): Disable --dj, print error, redirect to 4-stage pipeline
- Option 2 (Thin wrapper): Rewire --dj to call Stage 1 (mp3 reconcile/build) + Stage 2 (dj backfill) + Stage 3 (dj validate) + Stage 4 (dj xml emit)
- **Recommended:** Option 1 first (stop hiding the broken path), then consider Option 2

---

### Gap 2: Enrichment Timing Inconsistency

**Evidence:** DJ_WORKFLOW_AUDIT.md section 7

**Current Behavior:**
- Normal intake: background enrich/art launches after promote
- DJ intake (`--dj`): background enrich/art is suppressed

**Risk:** DJ-facing MP3s may be under-enriched vs master FLACs, metadata divergence.

**What to Do:**
- Enforce enrichment independent of DJ export flag
- Run enrichment before or after DJ build, never conditionally skip it
- Add regression test: compare enrichment results for DJ vs non-DJ path

---

### Gap 3: Retroactive MP3 Admission Untested

**Evidence:** MISSING_TESTS.md (P0 priority #1, P1 priority #4)

**Missing Tests:**
- `mp3 reconcile` + `dj backfill` on real MP3 directory
- Verify identity linkage is deterministic
- Verify reconcile_log records all decisions
- Verify duplicate/conflict handling

**Risk:** Can't reliably backfill existing MP3 library. Operators don't trust mp3 reconcile.

**What to Do:**
- Write integration test: create fixture MP3 directory, run reconcile, backfill, validate
- Verify manifest log, error handling, idempotency

---

### Gap 4: Rekordbox XML Determinism Under Patch

**Evidence:** MISSING_TESTS.md (P1 priority #6), REKORDBOX_XML_INTEGRATION.md

**Missing Tests:**
- emit → patch → re-emit, verify byte-identical XML or logically equivalent
- Verify TrackIDs are stable across patch cycles
- Verify playlist ordering is deterministic
- Verify manifest hash mismatch fails loudly
- Verify tampered XML blocks patch execution

**Risk:** Re-importing XML into Rekordbox corrupts cue points or loses track IDs.

**What to Do:**
- Write E2E test: full lifecycle (emit → library change → patch → re-emit)
- Assert stable TrackIDs, deterministic output

---

### Gap 5: CLI Help Text Parity

**Evidence:** AGENT.md (CLI help rules), DJ_WORKFLOW_AUDIT.md Task 2

**Risk:** Docs say `--dj` is legacy, but `tools/get --help` still presents it as primary.

**What to Do:**
- Update `tools/get --help` to mark `--dj` as deprecated
- Update all CLI help text to describe 4-stage pipeline as canonical
- Reference AGENT.md and DJ_WORKFLOW.md in help output

---

### Gap 6: Import Layering Not Linted

**Evidence:** PERPLEXITYREPORT (subsystem assumption), AGENT.md (no linting rule found)

**Risk:** Modules drift; tagslutcore could gain dependencies on tagslutdj, breaking layering.

**What to Do:**
- Add import linting rule (flake8-allowed-imports or similar)
- Enforce: tagslutcore* → can import from tagslutcore* and tagslut.storage
- Enforce: tagslutdj* → can import from tagslut.* except upward
- Document in AGENT.md

---

## 8.0 Schema Details & Ownership Rules

### Core Tables (Master Library & Identity)

#### `asset_file`
**Ownership:** Physical file facts only
**Key Fields:**
- id, path (UNIQUE), library, zone
- content_sha256, size_bytes, duration_s, sample_rate, bit_depth, bitrate
- flac_ok (boolean), integrity_state, integrity_checked_at
- first_seen_at, last_seen_at

**Constraint:** Path uniqueness enforced. Never use paths as identity.

#### `track_identity`
**Ownership:** Canonical recording identity
**Key Fields:**
- id, identity_key (UNIQUE)
- ISRC, beatport_id, tidal_id, spotify_id, musicbrainz_id, etc.
- artist_norm, title_norm, album_norm (searchable)
- canonical_title, canonical_artist, canonical_album, canonical_genre, canonical_bpm, canonical_key, canonical_label, canonical_year, canonical_duration
- canonical_payload_json (extended metadata, including lexicon_* keys from backfill)
- enriched_at, ref_source, duration_ref_ms
- merged_into_id (if merged), created_at, updated_at

**Constraint:** One row per distinct recording. Merges record loser in merged_into_id, winner becomes root.

#### `asset_link`
**Ownership:** Asset-to-identity binding
**Key Fields:**
- id, asset_id (UNIQUE), identity_id
- confidence, link_source, active

**Constraint:** UNIQUE(asset_id); each asset has exactly one active link.

#### `preferred_asset`
**Ownership:** Deterministic selection
**Key Fields:**
- identity_id (PK), asset_id
- score, version

**Constraint:** One per identity. Materialized view logic ensures it's computed from asset_link + quality rules.

---

### DJ Pipeline Tables (Stage 1: MP3 Registration)

#### `mp3_asset`
**Ownership:** Registered MP3 derivative facts
**Key Fields:**
- id, identity_id (FK), asset_id (FK, nullable)
- path (UNIQUE), content_sha256, size_bytes, bitrate, sample_rate, duration_s
- profile (standard, high-quality, etc.)
- status (unverified, verified, missing, superseded)
- source, zone
- transcoded_at, reconciled_at
- created_at, updated_at

**Indexes:** identity_id, zone, status

**Constraint:** One mp3_asset per MP3 file path. Status reflects readiness for admission.

#### `reconcile_log`
**Ownership:** Append-only audit log of reconciliation
**Key Fields:**
- id, run_id, event_time (DEFAULT CURRENT_TIMESTAMP)
- source (mp3_reconcile, manual, lexicondj, etc.)
- action (linked, skipped, conflict, backfill_metadata, backfill_tempomarkers, etc.)
- confidence (isrc_exact, title_artist_fuzzy, high, medium, low)
- mp3_path, identity_id, lexicon_track_id
- details_json

**Constraint:** Never update, only insert. Enables replay and audit of decisions.

---

### DJ Pipeline Tables (Stage 2–3: Curation & Admission)

#### `dj_admission`
**Ownership:** DJ library membership (curated subset)
**Key Fields:**
- id, identity_id (UNIQUE FK), mp3_asset_id (FK, nullable)
- status (pending, admitted, rejected, needs_review)
- source, notes, admitted_at
- created_at, updated_at

**Constraint:** UNIQUE(identity_id); one row per identity in DJ library.

#### `dj_track_id_map`
**Ownership:** Stable Rekordbox TrackID assignments
**Key Fields:**
- id, dj_admission_id (UNIQUE FK)
- rekordbox_track_id (INTEGER, UNIQUE)
- assigned_at

**Constraint:** UNIQUE(rekordbox_track_id); TrackID never reassigned for same admission.

**Invariant:** Ensures Rekordbox cue points survive re-imports.

#### `dj_playlist`
**Ownership:** Playlist hierarchy
**Key Fields:**
- id, name, parent_id (self-FK, nullable)
- lexicon_playlist_id (Lexicon cross-ref), sort_key
- playlist_type (standard, smart, etc.)
- created_at

**Constraint:** UNIQUE(name, parent_id) per hierarchy level.

#### `dj_playlist_track`
**Ownership:** Playlist membership (many-to-many)
**Key Fields:**
- playlist_id (FK), dj_admission_id (FK)
- ordinal (sort position)
- PRIMARY KEY (playlist_id, dj_admission_id)

**Constraint:** Deterministic ordering via ordinal field. Only references admitted tracks.

---

### DJ Pipeline Table (Stage 4: XML Export)

#### `dj_export_state`
**Ownership:** Export manifest and state
**Key Fields:**
- id, kind (rekordbox_xml, nml, m3u, etc.)
- output_path, manifest_hash (SHA-256)
- scope_json (filter/scope), emitted_at

**Constraint:** One row per emit/patch. Manifest hash enables tamper detection.

**Invariant:** `patch_rekordbox_xml()` verifies on-disk file matches manifest_hash before re-emitting.

---

## 9.0 Risk Assessment Matrix

### Critical Risks (Probability: High, Impact: Catastrophic)

| Risk | Evidence | Impact | Probability | Mitigation |
|---|---|---|---|---|
| **Two DJ paths create silent failures** | DJ_WORKFLOW_AUDIT.md (sections 2–4) + DJ_WORKFLOW_TRACE.md | Same operator command produces inconsistent DJ output; manual file handling required | High | Enforce deprecation or rewire tools/get --dj to canonical 4-stage |
| **Phase 1 stack merges out of order** | AGENT.md (phase rules), README.md (stack sync docs) | Dependencies break; PR #185 or #186 merge before #193 → schema mismatch | Medium-High | Use sync_phase1_prs.sh; enforce staged merge gate |
| **Rekordbox XML determinism fails under patch** | MISSING_TESTS.md (P1 #6), REKORDBOX_XML_INTEGRATION.md | Re-importing XML loses cue points, corrupts TrackID assignments, breaks re-import safety | High | Write E2E test: emit → patch → re-emit; assert stable IDs |

### High Risks (Probability: Medium, Impact: Major)

| Risk | Evidence | Impact | Probability | Mitigation |
|---|---|---|---|---|
| **Retroactive MP3 admission untested** | MISSING_TESTS.md (P0 #1, P1 #4) | Can't backfill existing DJ/MP3 library; operators distrust mp3 reconcile | High | Write integration test for reconcile + backfill with fixture MP3 directory |
| **Enrichment suppressed in DJ mode** | DJ_WORKFLOW_AUDIT.md (section 7) | DJ-facing MP3s under-enriched vs master FLACs; metadata divergence | Medium | Enforce enrichment independent of --dj flag; add regression test |
| **CLI help text misleads operators** | AGENT.md (CLI help rules), DJ_WORKFLOW.md (legacy section) | Users follow --help instead of docs; invoke broken --dj path | Medium-High | Update all CLI help to mark --dj deprecated, reference 4-stage pipeline |
| **Import layering drifts** | PERPLEXITYREPORT (assumption), no linting rule found | Circular dependencies; core modules depend on DJ layers | Medium | Add flake8-allowed-imports linting; enforce layering in CI |

### Medium Risks (Probability: Medium, Impact: Moderate)

| Risk | Evidence | Impact | Probability | Mitigation |
|---|---|---|---|---|
| **Test baseline diverges from actual state** | AGENT.md (test checklist), CI rules | Developers skip tests thinking they pass | Low-Medium | Sync test baselines before Phase 1 merge; enforce CI gating |
| **Lexicon backfill is 36% unmatched** | PROGRESS_REPORT.md (11,679 / 32,196 unmatched) | 1/3 of identities missing Lexicon enrichment | Medium | Consider fallback enrichment sources; document expected coverage |
| **Precheck-hit behavior is transient** | DJ_WORKFLOW_AUDIT.md (section 2) | Fallback transcoding/tag-matching produces different MP3s than canonical path | Medium | Add test comparing both paths; enforce consistency or unify |

---

## 10.0 Work Decomposition & Prioritization

### Phase 0: Verification (Weeks 1–2)

**Goal:** Confirm documented behavior actually exists in code.

#### Task 0.1: Verify CHANGELOG Claims
- [ ] Check tagslut/exec/mp3_build.py exists with claimed build/reconcile functions
- [ ] Check tagslut/dj/admission.py exposes admit/backfill/validate
- [ ] Check tagslut/dj/xml_emit.py exists with manifest integrity logic
- [ ] Check tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql matches schema docs
- [ ] Run claimed E2E tests, verify they pass or document failures
- **Output:** Verification report

#### Task 0.2: Audit CLI Help Text
- [ ] `tools/get --help` — does it mark --dj as deprecated?
- [ ] `tagslut mp3 --help` — does it describe build/reconcile?
- [ ] `tagslut dj --help` — does it list admit/backfill/validate/xml?
- [ ] README.md Stage descriptions — do they match CLI output?
- **Output:** CLI help audit report

#### Task 0.3: Trace Actual DJ Workflow Execution
- [ ] Run `tools/get <url>` (non-DJ) → document actual stages executed
- [ ] Run `tools/get <url> --dj` (new track) → document promotion-fed path
- [ ] Run `tools/get <url> --dj` (precheck-hit) → document precheck-hit fallback path
- [ ] Compare paths; document divergences against DJ_WORKFLOW_TRACE.md
- **Output:** Execution trace report with diffs

### Phase 1: Closure (Weeks 3–5)

**Goal:** Close critical test gaps. Enforce 4-stage pipeline contract.

#### Task 1.1: Write P0 Tests (Retroactive MP3 Admission)

**P0-A: tools/get --dj with precheck-hit inventory**
- Fixture: seed DB with existing tracks, precheck will return "already have"
- Action: run `tools/get <url> --dj` on precheck-hit scenario
- Assert: DJ copies are created AND match canonical path behavior
- **OR** assert: command fails loudly with guidance to use mp3 reconcile

**P0-B: tools/get --dj with empty PROMOTED_FLACS_FILE**
- Fixture: promotion produces zero results
- Action: `tools/get --dj` reaches DJ stage with empty file list
- Assert: command fails loudly or produces explicit zero-output message
- **NOT:** silent success with no DJ outcome

**P0-C: Promote-hit vs Precheck-hit Equivalence**
- Fixture: same logical track in two scenarios (new vs existing)
- Action: run both paths
- Assert: resulting dj_admission entries are identical, OR paths are documented as intentionally divergent

**Output:** Test suite passing (or clear list of intentional divergences)

#### Task 1.2: Write P1 Tests (Determinism & Reconciliation)

**P1-A: Existing MP3 Retroactive Admission**
- Fixture: 10 MP3 files in DJ root, unregistered
- Action: mp3 reconcile → dj backfill → dj validate
- Assert: all 10 matched to identities, admitted to DJ library, validation passes
- Assert: reconcile_log records all decisions (20+ rows)

**P1-B: Enrichment Timing Independence**
- Fixture: same intake run, compare enrichment results with/without --dj
- Action: preprocess root normally vs with --dj flag
- Assert: enrichment results are identical

**P1-C: Rekordbox XML Determinism**
- Fixture: stable dj_* state (no changes between runs)
- Action: emit → [no changes] → emit again
- Assert: output files are byte-identical
- Assert: TrackIDs are stable

**P1-D: Rekordbox XML Patch Integrity**
- Fixture: emitted XML + dj_export_state manifest
- Action: [tamper with on-disk XML] → patch command
- Assert: patch fails loudly with manifest mismatch error

**P1-E: Rekordbox XML Patch Preserves TrackIDs**
- Fixture: emit → admit new track → patch
- Assert: existing TrackIDs unchanged; new track gets fresh ID
- Assert: Rekordbox cue points survive (metadata preserved)

**Output:** E2E test suite covering all 4-stage scenarios

#### Task 1.3: Normalize Docs Around Single Contract
- [ ] Archive any doc that presents tools/get --dj as primary for curated DJ library
- [ ] Update REPORT.md to front-load legacy warning
- [ ] Update all examples to use 4-stage commands
- [ ] Create DJ_WORKFLOW_CURRENT.md (or refresh DJ_WORKFLOW.md) with canonical pipeline
- [ ] Update README.md DJ section
- **Output:** Docs describe single 4-stage contract consistently

#### Task 1.4: Update CLI Help & Error Messages
- [ ] tools/get --dj prints deprecation warning at startup
- [ ] tools/get --dj failure modes include link to 4-stage pipeline
- [ ] tagslut mp3 build/reconcile --help describes both options clearly
- [ ] tagslut dj [stage] --help includes example commands
- **Output:** Help text matches documented contract

### Phase 2: Enforcement (Weeks 6–8)

**Goal:** Remove parallel/misleading paths. Harden invariants.

#### Task 2.1: Deprecate or Rewire tools/get --dj
- **Option A (Recommended First):** Hard deprecation
  - Add error message: "tools/get --dj is deprecated. Use the 4-stage DJ pipeline instead: see docs/DJ_WORKFLOW.md"
  - Print to stderr at startup
  - Update docs to mark it as removed in future version

- **Option B (Long-term):** Thin wrapper
  - Rewire tools/get --dj to call mp3 reconcile/build + dj backfill + dj validate + dj xml emit
  - Document as a convenience alias
  - Ensure both paths produce identical results

**Output:** Chosen path implemented and tested

#### Task 2.2: Enforce Import Layering
- [ ] Add flake8 linting rule (flake8-allowed-imports)
- [ ] Define allowed imports by module group (core, dj, cli, etc.)
- [ ] Run linting in CI; fail on violations
- [ ] Document layering in AGENT.md
- **Output:** CI enforces layering; violations fail PR checks

#### Task 2.3: Harden Invariants via Tests
- [ ] dj_track_id_map stability: generate report showing ID reassignments (should be zero)
- [ ] XML determinism: run emit 10 times, hash each output, assert all hashes identical
- [ ] Manifest integrity: corrupt XML, run patch, assert failure
- [ ] Reconcile idempotency: run mp3 reconcile twice, assert same rows created second time
- **Output:** Invariant tests in CI; fail on violation

#### Task 2.4: Schema Migration Safeguards
- [ ] Make migration 0010 checkpoint mandatory
- [ ] Add pre/post migration validation to AGENT.md checklist
- [ ] Store checkpoints in version control (data/checkpoints/reconcile_schema_0010.json)
- [ ] Prevent schema changes without checkpoint
- **Output:** Migration process enforced; checkpoints tracked

### Phase 3: Integration (Weeks 9–12)

**Goal:** Reconcile real-world DJ/MP3 state. Implement Lexicon backfill as real operator workflow.

#### Task 3.1: Lexicon Reconciliation Program
- [ ] Implement lexicon_backfill.py using reconcile_log + dry-run + resumability
- [ ] Dry-run preview with match counts
- [ ] Execute mode with DB writes + reconcile_log entries
- [ ] Resume-from-checkpoint on failure
- [ ] Operate on real DJ directory + Lexicon DB
- **Output:** Live reconcile workflow; 20k+ identities enriched

#### Task 3.2: DJ Library Backfill from Existing State
- [ ] Scan existing DJ_LIBRARY directory
- [ ] mp3 reconcile to register all MP3s
- [ ] dj backfill to admit all verified assets
- [ ] dj validate to check readiness
- [ ] dj xml emit to produce Rekordbox XML from real state
- **Output:** Production DJ library state captured in DB

#### Task 3.3: Operator Runbook & Training
- [ ] Document complete 4-stage workflow with examples
- [ ] Create quick-start guide for new operators
- [ ] Record expected output for each stage
- [ ] Document failure modes and recovery procedures
- **Output:** ops/DJ_PIPELINE_RUNBOOK.md

---

## 11.0 Constraints for Claude Code (Operating Rules)

### Primary Constraints (Non-Negotiable)

#### C1: Trust AGENT.md as Primary Source
- Read AGENT.md first for all work
- When in doubt, defer to AGENT.md doctrine
- If CLAUDE.md and/or .codex/AGENT.md conflicts with AGENT.md, AGENT.md wins (except tool-specific behavior)

#### C2: Maintain Master → DJ Layering
- ✅ **DO** write changes to dj_* tables
- ✅ **DO** link DJ state to track_identity via identity_id
- ✅ **DO** treat master library as immutable source of truth
- ❌ **DON'T** mutate track_identity or asset_file to achieve DJ outcomes
- ❌ **DON'T** make master library depend on DJ success

#### C3: Use Explicit Commands, Not Hidden Paths
- ✅ **DO** call specific `tagslut mp3 build`, `tagslut dj admit`, etc.
- ✅ **DO** expose all transformations as explicit DB operations
- ✅ **DO** use reconcile_log to audit all decisions
- ❌ **DON'T** hide logic in wrapper scripts
- ❌ **DON'T** create implicit branching (different behavior based on hidden state)

#### C4: Enforce Dry-Run by Default
- ✅ **DO** make --dry-run the default behavior
- ✅ **DO** require explicit --execute to write
- ✅ **DO** show full plan before execution
- ❌ **DON'T** mutate state without user confirmation
- ❌ **DON'T** skip dry-run for "safe" operations

#### C5: Preserve Planning & Execution Separation
- ✅ **DO** store plans in DB before execution (move_plan, dj_export_state, etc.)
- ✅ **DO** make decisions (decide) separate from mutations (execute)
- ✅ **DO** write receipts after execution (move_execution, provenance_event)
- ❌ **DON'T** execute immediately; always offer dry-run first
- ❌ **DON'T** skip verification steps

#### C6: Enforce Database Integrity
- ✅ **DO** run migration verification checklist before/after schema changes
- ✅ **DO** use `PRAGMA foreign_keys = ON` for all connections
- ✅ **DO** call `PRAGMA integrity_check` after mutations
- ✅ **DO** save checkpoints after migrations
- ❌ **DON'T** skip integrity checks
- ❌ **DON'T** assume schema migrations are safe without verification

---

### Safety Rails (What to Avoid)

#### S1: Don't Assume tools/get --dj Reliability
- **Current State:** Two divergent code paths (promotion-fed vs precheck-hit)
- **Risk:** Same command produces inconsistent DJ output
- **Action:** If touching DJ intake, test both paths or explicitly unify them

#### S2: Don't Assume Enrichment Timing
- **Current State:** --dj flag suppresses background enrichment
- **Risk:** DJ-facing MP3s under-enriched vs master FLACs
- **Action:** Run enrichment independent of DJ export mode

#### S3: Don't Mutate files.dj_* Columns
- **Current State:** Legacy DJ state in files table
- **Planned:** Migrate to dj_* tables
- **Action:** Write to dj_admission, dj_track_id_map, dj_playlist* instead

#### S4: Don't Assume XML Reconstruction is Cheap
- **Current State:** XML is formal export; not internal working format
- **Risk:** Rebuilding XML may corrupt TrackIDs or cue points
- **Action:** Use dj_track_id_map for stable IDs; test patch cycles

#### S5: Don't Skip Validation Before Export
- **Current State:** dj validate checks missing files, empty metadata
- **Risk:** Silent failures in Rekordbox import
- **Action:** Always run validation; use --skip-validation only if explicitly documented

#### S6: Don't Reuse paths as Identity Anchors
- **Current State:** All identity truth is in track_identity table
- **Risk:** Path-based identity drifts with file moves
- **Action:** Use identity_id (from track_identity) as the stable reference

---

### Verification Checklist (Before Any Work)

Before beginning a task, verify:

- [ ] Read AGENT.md (sections 1–3: role, canonical surface, invariants)
- [ ] Read CLAUDE.md and/or .codex/AGENT.md if applicable (tool-specific rules)
- [ ] If DJ-related: Read DJ_WORKFLOW_AUDIT.md + GAP_TABLE.md (gap evidence)
- [ ] If schema-touching: Read DB_V3_SCHEMA.md + AGENT.md migration checklist
- [ ] If Phase 1 stack: Run `git fetch origin && git log --oneline origin/dev..HEAD` (upstream status)
- [ ] If tests: Check MISSING_TESTS.md for priorities
- [ ] Run `make doctor-v3 V3=<DB>` (schema validation)
- [ ] Run `poetry run pytest -q` (baseline test status)

---

## 12.0 Summary: Repo State vs Intended Architecture

### Alignment Table

| Dimension | Intended Architecture | Documented in Repo | Implemented in Code | Gap? | Mitigation |
|---|---|---|---|---|---|
| **DJ workflow structure** | 4-stage explicit pipeline | AGENT.md, README.md, DJ_WORKFLOW.md | Partially (2 hidden paths in tools/get --dj) | ⚠️ Yes | Deprecate --dj or rewire to 4-stage |
| **MP3 registration** | mp3_asset table, mp3 reconcile command | CHANGELOG.md, DB_V3_SCHEMA.md, DJ_WORKFLOW.md | Claimed (needs code verification) | ⚠️ Unverified | Task 0.1: Verify mp3_build.py + tests |
| **DJ admission** | dj_admission table, dj backfill command | CHANGELOG.md, DB_V3_SCHEMA.md, DJ_WORKFLOW.md | Claimed (needs code verification) | ⚠️ Unverified | Task 0.1: Verify admission.py + tests |
| **Rekordbox TrackID stability** | dj_track_id_map, dj_export_state, deterministic XML | REKORDBOX_XML_INTEGRATION.md, CHANGELOG.md | Claimed (determinism untested) | ⚠️ Untested | Task 1.2: Write E2E XML patch test |
| **Lexicon enrichment** | Lexicon_backfill.py with reconcile_log | PROGRESS_REPORT.md (20,517 enriched) | Executed (snapshot complete) | ✅ No | Task 3.1: Operationalize as repeatable workflow |
| **tools/get --dj deprecation** | Marked legacy with redirect to 4-stage | AGENT.md, README.md, DJ_WORKFLOW.md | Marked in docs; code unchanged | ⚠️ Incomplete | Task 1.4: Add deprecation warning + error messages |
| **Schema separation (master/MP3/DJ)** | Explicit tables per layer | DB_V3_SCHEMA.md, DATA_MODEL_RECOMMENDATION.md | Migration 0010 applied (schema exists) | ✅ No | Verify invariants via tests |
| **Planning/execution separation** | Dry-run first, explicit --execute | AGENT.md, README.md | Claimed in all commands | ⚠️ Unverified | Spot-check CLI flags on mp3/dj commands |
| **Import layering enforcement** | Core → DJ unidirectional | AGENT.md (no linting rule) | Not enforced | ❌ No | Task 2.2: Add flake8 linting rule |
| **Retroactive MP3 admission** | mp3 reconcile + dj backfill tested | MISSING_TESTS.md (P0/P1 listed) | Not tested | ❌ No | Task 1.1–1.2: Write fixture + integration tests |

---

## 13.0 Bottom Line for Claude Code

### What You Have

✅ **Excellent Strategic Documentation**
- AGENT.md defines core doctrine clearly
- 4-stage pipeline is explicitly designed
- Schema separation is ratified
- Failure mode (DJ workflow) is diagnosed
- Work orders are in prompt files

✅ **Partial Implementation**
- Schema migration 0010 applied (tables exist)
- Lexicon backfill executed (20,517 identities enriched)
- Audit documents produced (DJ_WORKFLOW_AUDIT.md, etc.)
- Phase 1 refactor in-flight

### What You Don't Have (Yet)

❌ **Complete Verification**
- Code behavior not confirmed against CHANGELOG claims
- CLI help text not audited for consistency
- Critical tests not written (retroactive MP3, XML patch determinism)
- Two DJ paths still exist in tools/get --dj

❌ **Full Integration**
- tools/get --dj still has two paths (not enforced)
- Lexicon reconcile not operationalized as repeatable workflow
- Existing DJ/MP3 library state not captured in DB
- Import layering not linted

### Your Mission

**Not to redesign. To verify and complete.**

Make the documented model **undeniably true** everywhere:
- ✅ **In code** (tagslut/exec/*, tagslut/dj/*, tagslut/cli/*)
- ✅ **In migrations** (0010, checkpoints)
- ✅ **In CLI help** (--help text matches docs)
- ✅ **In tests** (E2E scenarios from MISSING_TESTS.md)
- ✅ **In XML behavior** (determinism, stability, patches)
- ✅ **In operator experience** (single 4-stage workflow)

If something still depends on tools/get --dj behaving like a smart shortcut, that's a bug, not a feature. If XML can emit different outputs for the same DB state, that's a contract failure. If existing MP3 libraries can't be reconciled without manual archaeology, the system isn't finished.

The boring, reliable end state is clear:

**FLAC master truth → identity truth → MP3 derivative truth → DJ admission truth → Rekordbox XML projection truth.**

Everything else either supports those contracts or gets out of the way.

---

## Appendix A: Document Reading Order for New Contributors

### Onboarding Path (Day 1)

1. **AGENT.md** (full read, 1–2 hours) — Canonical doctrine
2. **README.md** (quick scan, 15 min) — Operator overview
3. **DJ_WORKFLOW.md** (skim, 20 min) — Current DJ pipeline reference

### Deep Dive (Days 2–3)

4. **CHANGELOG.md** (full read, 30 min) — Recent changes
5. **DJ_WORKFLOW_AUDIT.md** (full read, 45 min) — Problem diagnosis
6. **DB_V3_SCHEMA.md** (sections 1–3, 30 min) — Core + DJ tables
7. **Data_MODEL_RECOMMENDATION.md** (full read, 20 min) — Layering rationale

### Implementation Details (Days 4–5)

8. **MISSING_TESTS.md** (full read, 15 min) — Test gaps
9. **REKORDBOX_XML_INTEGRATION.md** (full read, 15 min) — XML contract
10. **Prompt files** (.github/prompts/) (skim, 30 min each) — Work orders

### Quick Reference (During Work)

- **AGENT.md** — Doctrine, constraints, git rules, migration checklist
- **CLAUDE.md and/or .codex/AGENT.md** — Procedural rules (docs-first, reversibility, etc.)
- **MISSING_TESTS.md** — Test priorities (P0, P1, P2)
- **DJ_WORKFLOW_GAP_TABLE.md** — Gaps at a glance (1 page)

---

**End of Supermassive Report**

**Report prepared:** March 15, 2026
**Sources:** ChatGPT strategic framework + PERPLEXITYREPORT + 6 audit docs + 4 active docs + handoff bundle metadata
**Total evidence base:** 20+ source documents verified and cross-referenced
