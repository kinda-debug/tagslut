# tagslut Metadata Stack: Implementation Plan (Final)

**Anchored to:** Public-GitHub report (commit `a060a2b`) + Local-repo report + OAS specs
**Produced:** 2026-03-19 | **Last updated:** 2026-03-20
**Status:** Phases 0, 1, 3a-3e complete. Phase 2 next.

---

## Architectural Foundations

### Dual-provider constraint

Strictly dual-provider: TIDAL + Beatport. All other providers removed from the identity model. Only two authoritative provider identifiers: `beatport_id` and `tidal_id`. Provider uniqueness fully enforceable at schema level.

### Parallel paths, shared identity contract

**Path A (intake):** Single-track direct ingestion via `identity_service.resolve_or_create_identity()`.
**Path B (batch CSV):** Bulk enrichment producing merged CSV, converging into the same identity service interface.

**Hard invariant:** `identity_service` is the sole writer to `track_identity`. Bypass is invalid. Both paths must produce identical state. Divergence is a defect.

### Resolution order

1. ISRC (when trusted) 2. Beatport ID 3. TIDAL ID 4. Fuzzy fallback

### Supabase transaction constraint

All critical write paths execute inside Postgres functions (RPC) or server-side transactions. PostgREST does not support client-side multi-step transactions. Partial writes = inconsistent identity state.

### Resolved prerequisites

TIDAL OAuth PKCE working. Legacy scope failure (`r_usr`/`w_usr`) identified and resolved. Bidirectional enrichment (Beatport <> TIDAL) in scope and unblocked.

---

## Execution Status

| Phase | Item | Status |
|---|---|---|
| 0 | `.gitignore` + `docs/reference/README.md` | **Done** |
| 1 | Contract docs (4 files in `docs/contracts/`) | **Done** |
| 2 | Archive + provider scope cleanup | Not started |
| 3a/3b | TIDAL transport audit (inline comments in `tidal.py`) | **Done** |
| 3c | Beatport auth fallback log level (WARNING not DEBUG) | **Done** |
| 3d | Beatport `/store/{isrc}/` endpoint test | Postman request ready, needs live run |
| 3e | Confidence normalization (enum in dataclasses, canonical dict in types.py) | **Done** |
| 3f | Convergence interface definition | Documented in architecture contract as O4 |
| 3g | Write-path atomicity audit | Skeleton in architecture contract, needs full audit |
| 4 | Test hardening | Not started |
| 5 | Bidirectional enrichment | Not started |

---

## Completed Work (Detail)

### Phase 0: Security Hygiene — Done

`.gitignore` updated with `*.har` and explicit entries for all security-sensitive files (`auth.txt`, `tidalhar.txt`, `tidalhar.md`, `tidal_tokens.json`, `tidal_tokens.txt`, `tidaltokens.md`, `tidal-api-oas.json`, `tidal-api-oas.md`, `beatport-v3.json`, `beatport-search.json`, `cff5a0f2f4c9b1545d5d.js`, `cff5a0f2f4c9b1545d5d.md`).

`docs/reference/README.md` created documenting local-only reference files and handling policy.

Git history check: none of these files were ever committed. No `git filter-repo` needed.

### Phase 1: Contract Docs — Done

Four files created under `docs/contracts/`:

`metadata_architecture.md` (primary): Identity key derivation, `resolve_or_create_identity()` guarantees, convergence invariant, Supabase atomicity audit table (skeleton), provider scope declaration (TIDAL + Beatport only).

`provider_matching.md` (shared infrastructure): TIDAL v2/v1 transport split, ISRC capability per method, auth requirements, Beatport v4/search/scraping split, `/v4/catalog/tracks/store/{isrc}/` discovery, rate limits.

`metadata_row_contracts.md` (batch interface): All four CSV schemas (`TIDAL_SEED_COLUMNS`, `TIDAL_BEATPORT_MERGED_COLUMNS`, `BEATPORT_SEED_COLUMNS`, `BEATPORT_TIDAL_MERGED_COLUMNS`) with column-level detail. Field mapping table to identity service parameters and `track_identity` columns.

`README.md` (governance): Contract docs are normative. Changes to identity resolution, schemas, matching, or confidence require contract doc update in the same PR.

### Phase 3a/3b: TIDAL Transport Audit — Done

Four inline comments added to `tidal.py` documenting: which methods use v2 (ISRC-capable via `filter[isrc]`), which use v1 (playlist export, no ISRC), and the no-migration-without-parity-validation constraint.

### Phase 3c: Beatport Auth Fallback Visibility — Done

Both `search_track_by_isrc` and `search_track_by_text` now log `WARNING` (not `DEBUG`) when Beatport catalog/search auth is absent. Auth loss is visible in production logs instead of silently swallowed.

### Phase 3d: Beatport ISRC Store Endpoint — Postman Ready

Request created in Postman collection. Set `beatport_test_isrc` to a known ISRC and run. Key question: does it return a single direct record (no pagination wrapper) vs. the `?isrc=` query-parameter approach which returns a `results` array? Direct record = cleaner integration point.

### Phase 3e: Confidence Normalization — Done

`CONFIDENCE_NUMERIC` dict now lives in `types.py` alongside the `MatchConfidence` enum -- the only correct home.

Both `TidalBeatportMergedRow.match_confidence` and `BeatportTidalMergedRow.match_confidence` changed from `float` to `MatchConfidence` enum fields.

Both provider files (`beatport.py`, `tidal.py`) had local `_FALLBACK_CONFIDENCE_NUMERIC` dicts removed; now import the canonical one from `types.py`.

All six call sites (3 per provider) now pass enum values directly. No more hard-coded `1.0` / `0.0`.

`enricher.py` serializes enum to float via `CONFIDENCE_NUMERIC` at CSV write time -- the only place that conversion should happen.

---

## Remaining Work

### Phase 2: Archive and Provider Scope Cleanup

**Step 2a: Doc archive.** Create `docs/archive/metadata-transition-2026-03-19/`. Move `Dual-SourceTIDALBeatportMetadataFlow.md`, `metadata.md`, `docs/beatport_provider_report.md`, `docs/tidal_beatport_enrichment.md` with one-line stubs pointing to contract docs. `docs/WORKFLOWS.md` stays normative.

**Step 2b: Provider scope cleanup.** Import sweep for all non-TIDAL/non-Beatport providers. Archive dropped provider files to `tagslut/legacy/dropped_providers_2026-03-19/`. Schema audit for orphaned provider columns.

**Step 2c: Legacy wrapper.** Deprecate and remove `tagslut/metadata/models.py` compatibility wrapper after import sweep.

**Step 2d: Shell scripts.** Verify harvest script status, archive if dead.

**Step 2e: Test verification** after each move.

### Phase 3 Remaining

**3f: Convergence interface definition.** Documented as O4 in architecture contract. Full specification of `resolve_or_create_identity()` parameters, guarantees, and same-track behavior pending.

**3g: Write-path atomicity audit.** Skeleton table in architecture contract. Needs method-by-method classification of `identity_service.py` writes as safe-single-row, unsafe-chained, or wrapped-in-RPC. ChatGPT deep research report contains a useful first-pass audit table for this (methods: `_create_identity`, `_merge_identity_fields_if_empty`, `resolve_or_create_identity`, `link_asset_to_identity`, `upsert_asset_link`).

### Phase 4: Test Hardening

**High priority:** Resolution path tests (full cascade), provenance safety, fuzzy threshold boundaries, convergence tests, confidence normalization tests, atomicity tests.

**Medium:** Auth-absent Beatport degradation, edge cases (multi-candidate ISRC, ties, malformed input).

**Lower:** Header stability regression.

### Phase 5: Bidirectional Enrichment

In scope, unblocked by TIDAL PKCE. Needs implementation brief for `enrich_beatport_seed_row`. Key constraint: TIDAL v2 `filter[isrc]` availability determines whether reverse ISRC lookup is possible or must fall back to text search.

---

## Open Items

**O1:** External CSV consumers — still unknown. Must identify before schema changes.

**O2:** Operator tooling audit — 12 files under `tools/review/`, status unconfirmed.

**O3:** Beatport `/v4/catalog/tracks/store/{isrc}/` — Postman request ready, needs live run.

**O4:** Batch CSV bridge to identity_service — does batch path currently write to `identity_service` or stop at CSV output? Gates whether convergence tests are immediately runnable.

---

## Risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | TIDAL v1 removal breaks playlist export | Medium | Phase 3a is audit, not migration. No removal without parity validation. |
| 2 | Beatport auth loss degrades pipeline silently | Medium | Phase 3c done: WARNING-level logging. |
| 3 | Beatport ISRC path endpoint different auth/rate-limit | Low-Med | Small batch test before switching. Keep query-param as fallback. |
| 4 | Archive moves break hidden imports | Low-Med | Phase 2a sweep includes CLI entrypoints, scripts, docs. |
| 5 | CSV schema change breaks consumers | Unknown | Phase 1 freezes schema. Identify consumers (O1). |
| 6 | Fuzzy thresholds produce bad matches | Medium | Phase 4 boundary tests. No changes without calibration. |
| 7 | Silent divergence between paths | High | Phase 4 convergence tests. Governance. Sole-writer invariant. |
| 8 | Non-atomic writes corrupt identity state | High | Phase 3g audit. Postgres function wrapping. Phase 4 atomicity tests. |
| 9 | Provider reduction leaves orphaned schema artifacts | Low | Phase 2b schema audit. |
