<!-- Status: Archived document. Historical prompt only; not authoritative for current implementation. -->

# Tagslut Repository Audit Prompt (v2 -- Phase 1 Aware)

## What changed from v1

v1 treated tagslut as a static codebase to audit for general health. v2 incorporates the Phase 1 execution program: the PR dependency chain, branch-truth gates, SQLite migration safety rules, the identity service contract, legacy mirror requirements, and the specific stage boundaries. The audit scopes now verify plan adherence and catch drift between plan intent and actual repo state.

---

## How to use

1. Open a new conversation.
2. Copy the entire `[PROMPT START]` to `[PROMPT END]` block.
3. Uncomment ONE scope block by removing its `<!-- -->` markers.
4. Attach the documents listed in that scope's "Required attachments."
5. For DEEP audits: also attach the actual source files referenced.
6. Run. Fix findings. Re-run same scope as regression. Move to next scope.

---

## Recommended pass order

| Pass | Scope | Why this order | Key question answered |
|------|-------|----------------|----------------------|
| 1 | P1 | Phase 1 progress audit. Before auditing code quality, verify what has actually landed on dev vs what the plan says should have landed. | "Is the repo where the plan says it should be?" |
| 2 | A + E | Surface consistency + doc drift. Now informed by which PRs have merged, catch docs that describe pre-Phase-1 or mid-Phase-1 state inaccurately. | "Do the docs match the current landed state?" |
| 3 | B2 | Schema audit against Phase 1 contract. Verify migration 0006 matches PLAN2.md spec, identity service matches the resolution contract, legacy mirrors are maintained. | "Does the schema do what Phase 1 requires?" |
| 4 | C (tools/get --dj) | Trace primary workflow. Now specifically check: does it use the identity service or bypass it? Does it maintain legacy mirrors? | "Does the daily workflow respect Phase 1 boundaries?" |
| 5 | J | Config/env fragility. The zone/env rename PR changed runtime behavior. Verify the rename landed cleanly and aliases resolve correctly. | "Did the env rename PR break anything silently?" |
| 6 | D | Safety invariants. Verify the Phase 1 invariants (move-only, receipt logging, etc.) AND the new ones (no ad-hoc identity writes, no merge-chasing outside service, no filesystem DJ discovery). | "Are both old and new safety rules enforced?" |
| 7 | C (promote) | Trace all three promotion paths. Check whether each one goes through the identity service or bypasses it. | "Do all write paths use the canonical service?" |
| 8 | H | Architecture debt, now focused on Phase 1 boundaries: is DJ code reading from v3 only or still touching files/library_tracks directly? | "Is the legacy-to-v3 migration boundary clean?" |
| 9 | I | Operational risk, with Phase 1 additions: backfill interruption, migration rollback, identity over-merge, legacy mirror drift. | "What fails during the Phase 1 transition?" |
| 10 | F + G | Deps + tests. Check specifically for Phase 1 test coverage: FLAC+MP3 twin test, merge test, backfill resumption, legacy parity. | "Are the Phase 1 done-gate tests implemented?" |

---

[PROMPT START]

```
You are auditing the **tagslut** repository in the context of its ongoing **Phase 1 execution program**. tagslut is a Python-based music library management and DJ pool orchestration toolkit for a 25,000+ track FLAC master library.

Phase 1 is a disciplined, PR-sliced program to canonize the v3 identity model without hard-cutting legacy tables. Your audit must verify both general repo health AND adherence to the Phase 1 plan and its invariants.

Your output must be structured, precise, and actionable. Every finding must reference specific files, functions, tables, commands, or document sections. No filler.

---

## Repository Identity

- **Name**: tagslut
- **Version**: 3.0.1 (mid-Phase 1 execution)
- **Stack**: Python 3.11+, Poetry, SQLite, Click CLI, Flask optional, FFmpeg, mutagen, rapidfuzz
- **Operator**: Single developer (Georges), CLI-driven, macOS, /Volumes/MUSIC/*

## Phase 1 Execution Context

### What Phase 1 is
Make the v3 identity model authoritative without hard-cutting legacy tables:
- `track_identity` = canonical recording row (keyed by `identity_key`)
- `asset_file` = physical file row
- `asset_link(active=1)` = authoritative file-to-recording bridge
- `files`, `library_tracks`, `library_track_sources` = compatibility mirrors, mandatory until v3-only reads are proven

### Phase 1 stage boundaries
- **Stage 0**: Branch truth gate + DB snapshot gate (pre-work verification)
- **Stage 1**: Restore CI signal on dev (no storage/model work)
- **Stage 2**: Canonize v3 recording identity (schema + service + backfill)
- **Stage 3**: Correctness/performance constraints + DJ readiness
- **Stage 4**: Docs update + Phase 2 seam

### Planned PR merge order
1. script/layout (no-op, already passing)
2. retire `dedupe` alias
3. recovery tombstone (decommission tagslut.recovery)
4. transcoder typing/lint (fix transcoder.py, report.py, test_review_app.py)
5. flac_scan_prep fix (missing contextlib import)
6. migration scaffold
7. zone/env rename (env_paths.py, _index_helpers.py, legacy alias warnings)
8. clean baseline snapshot
9. migration 0006 (schema-only: add label, catalog_number, canonical_duration_s, indexes, verification)
10. identity service (resolve_active_identity, resolve_or_create_identity, link_asset_to_identity, mirror_identity_to_legacy)
11. backfill command (deterministic, resumable, artifact-producing)
12. identity merge/collision handling
13. v3 DJ candidate export (read-only from v3)
14. AGENT/docs update
15. Phase 2 seam (ClassificationCandidate dataclass only)

### Phase 1 key invariants
- Branch truth must be proven before remediation (Stage 0.0 gate)
- CI signal restoration is separate from schema work (Stage 1 vs Stage 2)
- Schema PRs must stay schema-only (no service logic, no backfill)
- SQLite migration verification: FK enabled per connection, foreign_key_check, integrity_check, PRAGMA optimize
- merged_into_id remains INTEGER REFERENCES track_identity(id) (not identity-key-based)
- Only the identity service may chase merged_into_id
- Exact-vs-fuzzy identity resolution has a sharp boundary (exact: existing link, ISRC, provider IDs; fuzzy: normalized artist+title+duration)
- Fuzzy matches must not overwrite exact-provider fields unless target field is empty
- Backfill must be deterministic, resumable (--resume-from-file-id), and produce artifacts
- Legacy mirrors (files, library_tracks, library_track_sources) remain mandatory
- No filesystem heuristics in DJ candidate path after Phase 1 gate

### Phase 1 done gate (all must pass)
- CI green on dev
- migration 0006 succeeds on production-scale copy
- foreign_key_check + integrity_check pass post-migration
- backfill dry-run emits full artifacts
- backfill live run completes within error budget
- FLAC + MP3 twin test: one identity, two assets, two links
- DJ candidate export reads only v3
- legacy mirror parity tests pass
- EXPLAIN QUERY PLAN shows index use for ISRC/provider-ID lookups
- PRAGMA optimize completed after schema/index changes

### Phase 1 risk register
| Risk | Detection | Mitigation |
|------|-----------|------------|
| Redundant/wrong branch work | Stage 0.0 diff gate | Stop before remediation, rebranch from dev |
| Corrupt/FK-invalid DB | integrity/FK checks fail | Fix bootstrap or restore backup |
| Identity over-merge | Backfill artifact: near-collisions count | Exact-vs-fuzzy boundary, manual review set |
| Legacy mirror drift | Parity tests fail | Write-through mirror in identity service only |
| Batch lock contention | SQLite lock errors | busy_timeout, chunked transactions, resume |

---

## Canonical CLI surface (11 groups)

tagslut intake / index / decide / execute / verify / report / auth / dj / gig / export / init

## v3 Core tables

- asset_file (path, hashes, zone, format, size, mtime, duration, sample_rate, bit_depth, bitrate, download_source, mgmt_status)
- track_identity (identity_key UNIQUE, isrc, beatport_id, artist_norm, title_norm, duration_ref_ms, ref_source; Phase 1 adds: label, catalog_number, canonical_duration_s, provider IDs, merged_into_id)
- asset_link (asset_id FK, identity_id FK, confidence, link_source, active; unique pair)
- move_plan / move_execution / provenance_event (audit trail)
- Legacy mirrors: files, library_tracks, library_track_sources

## Env var alias chains

- MASTER_LIBRARY <- LIBRARY_ROOT <- VOLUME_LIBRARY
- DJ_LIBRARY <- DJ_MP3_ROOT <- DJ_LIBRARY_ROOT
- QUARANTINE_ROOT <- VOLUME_QUARANTINE <- $VOLUME_WORK/quarantine
- TAGSLUT_DB / V3_DB, STAGING_ROOT, ROOT_BP, ROOT_TD, PLAYLIST_ROOT, DJ_PLAYLIST_ROOT, FIX_ROOT, DISCARD_ROOT

## Documents attached

[LIST WHAT YOU ACTUALLY ATTACHED]

---

## AUDIT SCOPE

Uncomment exactly ONE scope block.

<!-- ============================================================
### SCOPE P1: Phase 1 Progress Audit

**Depth**: MODERATE
**Strictness**: STRICT
**Perspective**: MAINTAINER

**Required attachments**: PLAN.md, PLAN2.md, the Phase 1 narrative summary, AGENT.md, CHANGELOG.md, and a `git log --oneline --decorate -40 origin/dev` output

**Audit instructions**:

This is the most important first pass. Before auditing code quality, verify what has actually happened vs what the plan says should have happened.

1. **PR landing status**: For each of the 15 planned PRs in PLAN2.md merge order, determine: landed on dev? open as draft PR? exists as branch only? not started? Use git log, CHANGELOG.md, and any attached PR list.

2. **Stage boundary violations**: Has any storage/model work landed before Stage 1 was fully green? Has any DJ/export work landed before the schema+service+backfill chain?

3. **Plan drift**: Compare PLAN.md (earlier) vs PLAN2.md (canonical) vs the narrative summary. Are there contradictions? Has the plan evolved in ways not captured in PLAN2.md?

4. **Schema contract verification**: If migration 0006 has landed, verify it matches PLAN2.md spec:
   - Added: label, catalog_number, canonical_duration_s
   - Added: partial indexes
   - Added: verification path (FK enable, foreign_key_check, integrity_check, PRAGMA optimize)
   - NOT changed: merged_into_id remains INTEGER REFERENCES
   - NOT included: identity service logic, backfill logic

5. **Identity service contract**: If the identity service has landed, verify its public API matches PLAN2.md:
   - resolve_active_identity(conn, identity_id) -- note: integer ID, not identity_key
   - resolve_or_create_identity(conn, asset_row, metadata, provenance)
   - link_asset_to_identity(conn, asset_id, identity_id, confidence, link_source)
   - mirror_identity_to_legacy(conn, identity_id, asset_id | None)

6. **Done gate checklist**: For each of the 11 done-gate items, determine: implemented? test exists? passing? not started?

7. **Stale work detection**: Are there branches or worktrees that the narrative says were "packaged" but never merged? Are there PRs that have gone stale?

8. **Risk register status**: For each of the 5 risks in PLAN2.md, has the detection mechanism been implemented? Has any risk materialized?

Output a progress matrix:
| PR/Item | Plan Status | Actual Status | Gap | Action Needed |
============================================================ -->

<!-- ============================================================
### SCOPE A + E: Surface Consistency + Doc/Code Drift (Phase 1 Aware)

**Depth**: SURFACE
**Strictness**: STRICT
**Perspective**: OPERATOR

**Required attachments**: All docs/*.md, AGENT.md, Makefile, pyproject.toml, README.md, REPORT.md, CHANGELOG.md, PLAN2.md

**Audit instructions**:

Same as v1 scope A+E, but with these Phase-1-specific additions:

11. **Phase 1 terminology**: Do docs consistently use "identity_key" vs "recording_id" vs "identity_id"? The narrative says resolve_active_identity was corrected to accept integer identity IDs, not identity keys. Do docs reflect this?
12. **Legacy mirror references**: Do any docs describe `files` or `library_tracks` as "source of truth" rather than "compatibility mirror"? This is a Phase 1 invariant violation in docs.
13. **Retired patterns**: Do docs still describe direct writes to track_identity outside the identity service? This is a Phase 1 forbidden pattern.
14. **Stage 1 PR coverage**: The CHANGELOG shows 3.0.0 and 3.0.1. Do these entries cover the Stage 1 PRs (recovery decommission, transcoder lint, flac_scan_prep fix, zone/env rename)?
15. **AGENT.md Phase 1 rules**: Does AGENT.md include the branch truth gate, migration verification checklist, backfill resume procedure, and forbidden patterns listed in PLAN2.md Stage 4? If not, which are missing?
============================================================ -->

<!-- ============================================================
### SCOPE B2: Schema Audit Against Phase 1 Contract

**Depth**: DEEP
**Strictness**: STRICT
**Perspective**: MAINTAINER

**Required attachments**: PLAN2.md, PLAN.md, docs/CORE_MODEL.md, docs/DB_V3_SCHEMA.md
**Also attach source**: tagslut/storage/schema.py, tagslut/storage/v3/*.py, any migration files (tagslut/storage/migrations/), tagslut/storage/v3/identity_service.py (if exists)

**Audit instructions**:

1. **Migration 0006 vs plan**: Compare the actual migration file against PLAN2.md spec. For each planned addition (label, catalog_number, canonical_duration_s, merged_into_id, partial indexes, verification path), verify: present? correct type? correct constraints?

2. **Columns already present vs added**: The narrative says "some canonical/provider columns were already present before the PR." Identify which track_identity columns existed pre-0006 vs which 0006 added. Does PLAN2.md's spec account for pre-existing columns?

3. **merged_into_id contract**: Verify merged_into_id is INTEGER REFERENCES track_identity(id), nullable, with no self-referential constraint in schema. Is the "merged rows cannot be merge targets" invariant enforced in schema (CHECK constraint) or only in application logic?

4. **asset_link uniqueness**: "At most one active asset_link per asset" -- is this enforced by a UNIQUE partial index on (asset_id) WHERE active=1, or application logic only?

5. **Identity service API shape**: If identity_service.py exists, verify:
   - resolve_active_identity accepts integer identity_id (not identity_key)
   - Resolution order: existing link -> ISRC -> provider IDs -> fuzzy -> create
   - Fuzzy does not overwrite exact-provider fields unless target empty
   - mirror_identity_to_legacy writes to files, library_tracks
   - No other module imports merged_into_id or chases merge chains

6. **Legacy mirror completeness**: PLAN.md says files.canonical_*, provider IDs, isrc, and dj_pool_path should be mirrored. Is mirror_identity_to_legacy actually writing all of these?

7. **FK enforcement**: Does migration_runner.py enable foreign keys before running checks? Is this per-connection (as required by SQLite semantics) or global?

8. **CORE_MODEL.md alignment**: Does the CORE_MODEL ownership table reflect Phase 1 reality? Specifically:
   - Does it mention legacy mirrors?
   - Does it mention the identity service as the sole write path?
   - Does it mention merged_into_id?
============================================================ -->

<!-- ============================================================
### SCOPE C: Workflow Trace -- tools/get <url> --dj (Phase 1 Aware)

**Depth**: DEEP
**Strictness**: STANDARD
**Perspective**: OPERATOR

**Required attachments**: docs/WORKFLOWS.md, docs/OPERATIONS.md, docs/DJ_WORKFLOW.md, AGENT.md, PLAN2.md
**Also attach source**: tools/get, tools/get-intake, tagslut/cli/commands/intake.py, tagslut/exec/transcoder.py, tagslut/storage/v3/identity_service.py (if exists)

**Audit instructions**:

Same workflow trace as v1, but with Phase 1 verification overlay:

11. **Identity service usage**: Does tools/get use the identity service for resolve_or_create_identity and link_asset_to_identity? Or does it still do ad-hoc writes to track_identity/asset_link/files?
12. **Legacy mirror maintenance**: After promote, does the flow call mirror_identity_to_legacy? Or does it write to files directly?
13. **DJ transcode path**: Does --dj read DJ candidates from v3 tables only, or does it fall back to filesystem heuristics or files table queries?
14. **Backfill interaction**: If a track is downloaded that already has a files row but no track_identity, does tools/get create the identity? Or is that left for the backfill command?
15. **Phase 1 forbidden patterns**: Does the workflow contain any of these:
    - Direct writes to track_identity outside identity service
    - Merge-chasing outside identity service
    - Per-file library_track_sources lookups in loops
    - Filesystem-based DJ candidate discovery
============================================================ -->

<!-- ============================================================
### SCOPE J: Config/Env Fragility (Phase 1 Aware)

**Depth**: MODERATE
**Strictness**: STRICT
**Perspective**: OPERATOR

**Required attachments**: docs/OPERATIONS.md, docs/WORKFLOWS.md, AGENT.md, README.md, docs/ZONES.md
**Also attach source**: tools/get (header), tagslut/utils/env_paths.py (if exists)

**Audit instructions**:

Same as v1 scope J, plus:

9. **Zone/env rename PR impact**: The narrative says this PR "introduced narrow warning behavior for legacy environment variable aliases while preserving canonical env precedence." Verify:
   - Which env vars were renamed?
   - Do the warnings actually fire at runtime, or are they compile-time only?
   - If a user has the old var name in .env but not the new one, does the system use the old value with a warning, or fail?
   - Is the precedence order documented anywhere?

10. **Phase 1 env additions**: Does Phase 1 introduce any new env vars (e.g., for backfill checkpoint paths, migration DB path)? Are they documented?

11. **DB path consistency**: TAGSLUT_DB vs V3_DB -- the narrative and PLAN2.md both reference these. In the bootstrap blocks, is the relationship always V3_DB=${V3_DB:-$TAGSLUT_DB} or the reverse? Does any code assume one but not the other?
============================================================ -->

<!-- ============================================================
### SCOPE D: Safety Invariants (Phase 1 Combined)

**Depth**: DEEP
**Strictness**: STRICT
**Perspective**: MAINTAINER

**Required attachments**: docs/ARCHITECTURE.md, PLAN2.md, AGENT.md
**Also attach source**: tagslut/exec/engine.py, tagslut/storage/v3/identity_service.py (if exists), tagslut/exec/transcoder.py

**Audit instructions**:

Verify BOTH the pre-Phase-1 safety rules AND the Phase 1 additions:

**Pre-Phase-1 rules** (from ARCHITECTURE.md):
1. Move-only semantics (no source deletion)
2. Pre-move checksums
3. Post-move checksums
4. Receipt logging (every move -> move_execution row)
5. Database as truth (asset_file.path updated after move)
6. Idempotent operations (safe to retry)

**Phase 1 additions** (from PLAN2.md):
7. No ad-hoc writes to track_identity (only through identity service)
8. No merge-chasing outside identity service
9. No per-file library_track_sources lookups in loops
10. No filesystem-based DJ candidate discovery after Phase 1 gate
11. Backfill must be resumable and artifact-producing
12. Legacy mirrors must be maintained on every write
13. SQLite FK enforcement per connection in migration/verification paths

For each rule: enforced in code? enforced by test? documented? violated anywhere?
============================================================ -->

<!-- ============================================================
### SCOPE C: Workflow Trace -- Promotion Paths (Phase 1 Aware)

**Depth**: DEEP
**Strictness**: STRICT
**Perspective**: MAINTAINER

**Required attachments**: docs/WORKFLOWS.md, docs/OPERATIONS.md, AGENT.md, PLAN2.md
**Also attach source**: tagslut/cli/commands/execute.py, tools/review/promote_by_tags.py, tools/review/promote_replace_merge.py, tools/get (promote section), tagslut/storage/v3/identity_service.py (if exists)

**Audit instructions**:

Same as v1 promotion trace, plus Phase 1 overlay:

6. **Identity service integration**: For each of the 3 promotion paths, does it call through the identity service, or does it write directly to asset_file/track_identity/files?
7. **Legacy mirror write-through**: After promotion, which paths update the legacy mirrors? Which skip it?
8. **Phase 1 invariant**: "Every accepted master FLAC has an asset_file row, an active asset_link, and a canonical track_identity." Is this guaranteed by all 3 promotion paths? Or only some?
9. **Backfill gap**: If a file is promoted before backfill has run, does the promotion path create the identity? Or does it leave an asset_file with no identity, creating an orphan?
============================================================ -->

<!-- ============================================================
### SCOPE H: Architecture Debt (Phase 1 Aware)

**Depth**: DEEP
**Strictness**: STANDARD
**Perspective**: MAINTAINER

**Required attachments**: docs/ARCHITECTURE.md, docs/CORE_MODEL.md, AGENT.md, PLAN2.md, pyproject.toml
**Also attach**: tagslut/ directory tree (2 levels), identity_service.py if exists, any file that imports from tagslut.storage.v3

**Audit instructions**:

Same as v1 scope H, plus:

10. **Identity service isolation**: Does any module outside tagslut/storage/v3/ directly query track_identity, asset_link, or reference merged_into_id? (Phase 1 forbids this.)
11. **Legacy read paths**: Which modules still read from `files` or `library_tracks` directly? Is this documented as intentional (Phase 1 allows reads from legacy during transition) or accidental?
12. **DJ code v3 readiness**: Does tagslut/dj/ or scripts/dj/ read from v3 tables (asset_file, track_identity, asset_link) or from legacy tables (files, library_tracks)? Phase 1 requires at least one DJ candidate path that reads v3 only.
13. **Dual-write verification**: Is there any code path that writes to v3 tables but NOT to legacy mirrors? This would cause legacy mirror drift (Phase 1 risk).
============================================================ -->

<!-- ============================================================
### SCOPE I: Operational Risk (Phase 1 Aware)

**Depth**: MODERATE
**Strictness**: STANDARD
**Perspective**: OPERATOR

**Required attachments**: docs/ARCHITECTURE.md, docs/TROUBLESHOOTING.md, docs/WORKFLOWS.md, AGENT.md, PLAN2.md

**Audit instructions**:

Same as v1 scope I scenarios 1-12, plus Phase 1 transition risks:

13. **Backfill interruption**: Backfill is specified as resumable with --resume-from-file-id. If interrupted mid-batch, what state is left? Are partial batches committed or rolled back? Can resume produce duplicates?
14. **Migration 0006 failure mid-run**: ADD COLUMN is not transactional in SQLite. If migration fails after adding some columns but before others, what's the recovery path? Is the migration idempotent (safe to re-run)?
15. **Identity over-merge**: Fuzzy match incorrectly merges two distinct recordings. Detection is via backfill artifacts. But what's the UNDO path? Is there a command to unmerge (clear merged_into_id, relink assets)?
16. **Legacy mirror drift during transition**: During the period between identity service landing and backfill completion, writes go through the service (maintaining mirrors) but existing data hasn't been backfilled. Is there a parity check that detects partial backfill state?
17. **Concurrent tools/get + backfill**: If an operator runs tools/get while backfill is running, can they create conflicting identity rows? Is busy_timeout sufficient or do they need explicit locking?
18. **Phase 1 rollback**: If Phase 1 needs to be fully reverted, what's the procedure? Can migration 0006 be reversed? Are the added columns nullable (and thus ignorable by pre-Phase-1 code)?
============================================================ -->

<!-- ============================================================
### SCOPE F + G: Deps + Tests (Phase 1 Aware)

**Depth**: MODERATE
**Strictness**: STANDARD
**Perspective**: CONTRIBUTOR

**Required attachments**: pyproject.toml, Makefile, AGENT.md, PLAN2.md
**Also attach**: tests/ directory listing, conftest.py, .github/workflows/test.yml

**Audit instructions**:

Same as v1 scope F+G, plus Phase 1 test verification:

11. **Done-gate test coverage**: PLAN2.md specifies 11 done-gate items. For each, is there an existing test? Map:
    - Migration 0006 upgrade test
    - foreign_key_check + integrity_check post-migration
    - Backfill dry-run artifact emission
    - FLAC + MP3 twin test (one identity, two assets, two links)
    - Matching precedence tests (ISRC hit, provider ID hit, fuzzy fallback)
    - Merge test (duplicate ISRC collapse via merged_into_id)
    - Compatibility test (files.library_track_key matches track_identity)
    - Provenance test (library_track_sources still queryable)
    - DJ readiness test (select from v3 without filesystem heuristics)
    - Legacy mirror parity test
    - EXPLAIN QUERY PLAN index verification

12. **Test isolation from volumes**: Do Phase 1 tests require mounted volumes or actual music files? Can they run in CI with fixtures only?

13. **Transcoder regression test**: The narrative mentions "a narrow regression test proving DJ-managed frames are stripped while non-DJ custom frames survive." Does this test exist? What does it actually assert?
============================================================ -->

---

## Output Format

### [Scope Letter]. [Scope Name]

**Method**: What you compared, traced, or searched for.

**Findings** (CRITICAL > HIGH > MEDIUM > LOW):

| # | Severity | Confidence | Location | Finding | Evidence | Recommendation |
|---|----------|------------|----------|---------|----------|----------------|
| 1 | CRITICAL | HIGH | `file:section` | [Description] | [Observed vs expected] | [Specific fix] |

Confidence: HIGH = verified in 2+ sources. MEDIUM = 1 source + inference. LOW = inference only, mark UNVERIFIED.

**Phase 1 Impact**: For each finding, note whether it blocks Phase 1 progress, degrades a Phase 1 invariant, or is independent of Phase 1.

**Assumptions**: What you could not verify.

**Summary**: 2-3 sentences. The single most important thing to fix.

## Constraints

- Every finding must cite a specific file, section, line, command, or table.
- Do not recommend "add tests" without naming the exact function and invariant.
- Do not recommend "improve docs" without quoting the specific wrong/stale text.
- Do not flag style issues unless they mask correctness or safety bugs.
- Mark speculative findings as UNVERIFIED.
- Severity: CRITICAL = blocks Phase 1 or risks data loss. HIGH = degrades Phase 1 invariant or wastes significant operator time. MEDIUM = inconsistency. LOW = cosmetic.
- If you need source files you don't have, say so in Assumptions.
```

[PROMPT END]

---

## Post-audit maintenance

- Save findings: `artifacts/audit/pass_N_scope_X_YYYY-MM-DD.md`
- After Scope P1: update the "Phase 1 Execution Context" section with actual PR landing status before running subsequent scopes.
- After Scope J: save env var catalog as `docs/ENV_REFERENCE.md` for use in all subsequent passes.
- After Scope B2: if schema drift is found, update PLAN2.md before proceeding to workflow traces.
- Re-run a scope after fixing its findings before moving to the next scope.
- If any scope produces >15 findings, split it rather than accepting shallow coverage.

## When to update this prompt

- After each major PR lands on dev (update "Phase 1 Execution Context")
- After Phase 1 done gate passes (retire Phase 1 scopes, add Phase 2 scopes)
- After any plan revision (update invariants, merge order, done gate)
