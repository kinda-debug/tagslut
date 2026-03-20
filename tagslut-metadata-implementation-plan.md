# tagslut Metadata Stack: Implementation Plan (Final)

**Anchored to:** Public-GitHub report (commit `a060a2b`) + Local-repo report + OAS specs
**Produced:** 2026-03-19
**Status:** All architectural decisions resolved. Ready for delegation.

---

## Architectural Foundations

### Dual-provider constraint

The system is strictly dual-provider: TIDAL + Beatport. All other providers have been removed from the identity model. They are no longer used for identity resolution, uniqueness, or merge logic. This is a deliberate simplification, not a temporary reduction.

Only two authoritative provider identifiers remain: `beatport_id` and `tidal_id`. Provider uniqueness is fully enforceable at the schema level without exceptions or soft identifiers.

### Parallel paths, shared identity contract

Two ingestion paths converge on a shared identity contract:

**Path A (intake):** Single-track, direct ingestion. `tagslut intake` calls providers and `identity_service.resolve_or_create_identity()` directly. No CSV intermediate.

**Path B (batch CSV):** Bulk enrichment. TIDAL playlist export produces seed CSV, Beatport enrichment produces merged CSV. Output must converge into the same identity service interface.

**Hard invariant:** `identity_service` is the sole writer to `track_identity`. Any path that bypasses it is invalid. Both paths must produce identical `track_identity` state for identical input. With only two providers, divergence between paths is a defect, not a tolerable edge case.

### Resolution order

Deterministic, no cross-provider ambiguity:

1. ISRC (when trusted)
2. Beatport ID
3. TIDAL ID
4. Fuzzy fallback

### Confidence representation

Currently mixed: `MatchConfidence` enum internally, numeric values (1.0/0.6/0.0) in CSV output. Requirement: normalization must happen at the identity layer before persistence. The DB stores a single canonical representation.

### Supabase transaction constraint

The system runs on Supabase (Postgres), which materially affects write guarantees. Supabase uses PostgREST, meaning client-side multi-step transactions are not supported directly. Complex atomic operations must be implemented either inside Postgres functions (RPC) or via a direct DB connection (psycopg / server-side).

This constraint is architecturally load-bearing. The invariants above (atomic writes, merges, identity resolution, convergence) are only valid because all critical write paths execute inside the database layer or server-side, not via naive client chaining. Without this, Supabase would allow partial writes and inconsistent identity state.

This applies specifically to: merge operations, identity resolution + linking, multi-step updates, and any write that touches more than one row or table as part of a logical unit.

### Resolved prerequisites

TIDAL OAuth PKCE is working. Tokens are valid and usable. Callback confirmed. Earlier failures were caused by invalid legacy scopes (`r_usr`, `w_usr`), not app configuration. This removes the only real blocker on TIDAL-side ingestion and bidirectional enrichment.

---

## Section 1: Key Findings

**1.** The metadata architecture is real and substantial: v3 identity model, stable vendor row types, ISRC-first resolution. Both reports confirm this from direct code observation.

**2.** Transition-state drift remains the strongest structural risk. The TIDAL provider's v2/v1 hybrid transport is the clearest code-level signal. The gap between older one-way metadata prose and newer dual-source docs is the clearest doc-level signal.

**3.** The TIDAL provider's ISRC capability depends on which transport is active. v2 supports `filter[isrc]` on `GET /tracks`. v1 does not (client-side filtering on text search). The Dual-Source doc's "no dedicated ISRC endpoint" describes v1; the public report's `filter[isrc]` observation describes v2. This tension must be resolved.

**4.** The Beatport provider's ISRC capability is auth-dependent. Without a v4 token, ISRC matching is unavailable and all matches fall back to title/artist via web scraping. The Beatport v4 OAS reveals `/v4/catalog/tracks/store/{isrc}/` as a dedicated path-based ISRC lookup endpoint not discussed in either report. With only two providers, ISRC resolution quality is central to system correctness, making this endpoint high-priority.

**5.** The confidence system has a design-code gap (enum computed, hard-coded values written). Normalization must happen at the identity layer before persistence. Resolved as a design decision, pending implementation.

**6.** Security-sensitive artifacts exist locally: `tidalhar.txt` (~90+ auth-related strings), `cff5a0f2f4c9b1545d5d.js` (Beatport OAuth patterns, CLIENT_ID/CLIENT_SECRET), `auth.txt` (TIDAL login page config). Must be handled in Phase 0.

**7.** The metadata design docs (`metadata.md`, `Dual-SourceTIDALBeatportMetadataFlow.md`) are research/planning artifacts, not contracts. `docs/WORKFLOWS.md` remains normative until explicitly replaced.

**8.** Bidirectional enrichment (Beatport seeds TIDAL-enriched) is in scope. TIDAL PKCE resolved, scope limited to two providers, remaining work is implementation.

**9.** The provider reduction materially simplifies the system: two-provider identity model, deterministic resolution, reduced merge edge cases, stronger validation, simpler convergence enforcement.

**10.** The Supabase transaction constraint means that correctness depends on enforcing atomic writes at the database layer, not just application logic. Every write path identified in this plan must be evaluated for whether it executes atomically via Postgres function or server-side transaction, and any that rely on naive PostgREST client chaining must be flagged and rewritten.

---

## Section 2: Issues List

### Issue 1: Security -- HAR and auth artifacts contain live credentials

**Description:** `tidalhar.txt` (~90+ auth-related strings), `cff5a0f2f4c9b1545d5d.js` (Beatport OAuth flow, CLIENT_ID/CLIENT_SECRET), `auth.txt` (TIDAL login config).

**Type:** Security. **Urgency:** Immediate.

---

### Issue 2: TIDAL v2/v1 hybrid transport and ISRC capability tension

**Description:** v2 handles lookup/search with `filter[isrc]`. v1 handles playlist export with no ISRC capability. v1 is a legacy implementation detail, not a platform requirement; no migration without parity validation. ISRC behavior depends on which transport is active.

**Type:** Contract gap + code-doc drift

**Impact:** ISRC resolution silently degrades to text search on v1 code paths. With only two providers, every ISRC miss is a direct quality loss.

---

### Issue 3: Beatport auth-dependent capability + undiscovered ISRC endpoint

**Description:** ISRC search requires v4 auth. Without it, fallback is web-scraping (no ISRC). `/v4/catalog/tracks/store/{isrc}/` exists as a dedicated path-based lookup, untested, high priority.

**Type:** Contract gap

**Impact:** Auth loss silently disables ISRC matching for one of only two providers.

---

### Issue 4: Confidence representation not unified

**Description:** Enum computed internally, hard-coded numerics written to output. Normalization at the identity layer before persistence is a requirement, not optional.

**Type:** Contract gap (resolved decision, pending implementation)

---

### Issue 5: Metadata docs are not contracts

**Description:** `metadata.md` and `Dual-SourceTIDALBeatportMetadataFlow.md` are planning artifacts. `docs/WORKFLOWS.md` remains normative.

**Type:** Code-doc drift

---

### Issue 6: No convergence interface defined between paths

**Description:** Both paths must write to `track_identity` via `identity_service`, but the convergence interface is not documented. Given the Supabase constraint, the convergence interface must also specify which operations require Postgres function encapsulation vs. single-row PostgREST calls.

**Type:** Contract gap / governance

**Impact:** Highest-leverage risk. Two paths, one store, no convergence spec, and a platform that does not support client-side multi-step transactions.

---

### Issue 7: Write-path atomicity not audited against Supabase constraint

**Description:** The hard invariant says `identity_service` is the sole writer and writes must be atomic. But it is not yet verified which `identity_service` methods currently execute inside Postgres functions vs. which chain multiple PostgREST calls client-side. Any method that does the latter is a correctness risk: partial writes, inconsistent state, broken merge semantics.

**Type:** Contract gap / infrastructure

**Impact:** High. The entire convergence and merge model depends on this. If `resolve_or_create_identity()` chains client-side calls without wrapping them in a transaction, the identity layer's guarantees are illusory.

---

### Issue 8: Dropped providers must be archived, not just deprecated

**Description:** With provider reduction, `apple_music.py`, `itunes.py`, `spotify.py`, `qobuz.py`, `musicbrainz.py`, `traxsource.py`, `deezer.py` are explicitly out of scope. Archive, not deprecate. Same for schema columns, helpers, or test fixtures referencing them.

**Type:** Legacy/cleanup (clear mandate from architectural decision)

---

### Issue 9: Legacy compatibility wrapper `models.py`

**Description:** Coexists with structured `models/types.py` and `models/precedence.py`.

**Type:** Legacy/cleanup

---

### Issue 10: Shell harvest scripts with unclear status

**Description:** `beatport_harvest_catalog_track.sh` and `beatport_harvest_my_tracks.sh` alongside Python providers.

**Type:** Legacy/cleanup

---

### Issue 11: No canonical contract docs exist

**Description:** Root cause of doc drift. Two-provider constraint makes this easier to fix.

**Type:** Governance

---

### Issue 12: Test coverage gaps

**Description:** Missing: resolution path selection, auth-absent degradation, full identity cascade, provenance safety, fuzzy boundaries, multi-candidate ISRC, path convergence, and atomicity verification (that write paths actually execute inside transactions, not just that they produce correct results when nothing fails mid-write).

**Type:** Testing

---

### Issue 13: Bidirectional enrichment not yet implemented

**Description:** In scope and unblocked. Beatport-origin enrichment with TIDAL data. TIDAL PKCE resolved. Two-provider scope simplifies design.

**Type:** Contract gap (planned, unblocked)

---

### Issue 14: Fuzzy thresholds lack calibration

**Description:** `FUZZY_DURATION_TOLERANCE_S = 2.0`, `FUZZY_SCORE_THRESHOLD = 0.92`. No calibration data. With only two providers, false matches or rejections have outsized impact.

**Type:** Contract gap / testing

---

### Issue 15: Operator tooling not yet audited

**Description:** 12 files under `tools/review/`. Active/dead status unknown.

**Type:** Governance

---

### Issue 16: External CSV consumers unknown

**Description:** Downstream tools reading enriched CSVs need identification before schema changes.

**Type:** Governance

---

## Section 3: Implementation Plan

### Phase 0: Security Hygiene (immediate, no dependencies)

**Goals:** Eliminate credential exposure risk.

TIDAL tokens: PKCE flow is working with valid tokens. HAR file contains older browser-captured tokens, likely from a previous auth flow. Verify expiry status; rotate if any doubt.

Beatport: Verify whether CLIENT_SECRET references in `cff5a0f2f4c9b1545d5d.js` are actual secrets or public web bundle constants. Rotate if actual.

Add `tidalhar.txt`, `auth.txt`, `cff5a0f2f4c9b1545d5d.js`, `*.har`, and OAS spec files to `.gitignore`. Check git history with `git log --all --full-history`. Use `git filter-repo` if any were committed.

Create `docs/reference/README.md` for local-only reference files.

---

### Phase 1: Contract Freeze

**Goals:** Establish canonical contracts for a two-provider system with Supabase-aware write semantics.

**Document hierarchy:**

`docs/contracts/metadata_architecture.md` **(primary):** `track_identity` as canonical store. Provider scope: TIDAL + Beatport only, all others explicitly out of scope. `identity_key` derivation: ISRC (trusted) > `beatport_id` > `tidal_id` > fuzzy. `resolve_or_create_identity()` behavior and guarantees. Hard invariant: `identity_service` is sole writer; bypass is invalid. Convergence guarantee: both paths produce identical state. Confidence normalization requirement at DB layer. Fuzzy thresholds (documented as uncalibrated). Supabase transaction model: which write operations require Postgres function encapsulation, which are safe as single PostgREST calls, and which must use direct DB connections. This section is the architectural authority for write-path correctness.

`docs/contracts/provider_matching.md` **(shared infrastructure):** TIDAL: v2 for lookup/search (including `filter[isrc]`), v1 for playlist export (legacy, no ISRC). TIDAL PKCE auth: working, valid scopes documented, legacy scopes (`r_usr`, `w_usr`) explicitly invalid. Beatport: v4 catalog (auth required for ISRC), search service (no ISRC filter), web-scraping fallback (no ISRC). `/v4/catalog/tracks/store/{isrc}/`: discovered, untested, high priority. Match precedence: ISRC first, title/artist fallback second, no-match third. Auth-dependent capability: Beatport ISRC requires v4 token.

`docs/contracts/metadata_row_contracts.md` **(batch interface):** CSV schemas: `TIDAL_SEED_COLUMNS`, `TIDAL_BEATPORT_MERGED_COLUMNS`. Scoped to TIDAL + Beatport fields only; dropped-provider columns flagged for removal. Confidence mapping: 1.0/0.6/0.0 as interim, to be replaced when enum is wired. Explicit statement: CSV is the batch interface; `metadata_architecture.md` is canonical. Field mapping table: CSV column to identity service parameter to `track_identity` column.

**Validation:** Reviewable against code at `a060a2b`. Unverifiable claims flagged as "planned."

---

### Phase 2: Archive and Provider Scope Cleanup

**Goals:** Archive superseded docs. Execute provider reduction in code. This is an architectural decision, not a deprecation.

**Prerequisite:** Phase 1 complete.

**Doc archive:**

Create `docs/archive/metadata-transition-2026-03-19/`. Move with stubs:

`Dual-SourceTIDALBeatportMetadataFlow.md`: "Archived. Current: docs/contracts/provider_matching.md"

`metadata.md`: "Archived. Current: docs/contracts/"

`docs/beatport_provider_report.md`: Historical.

`docs/tidal_beatport_enrichment.md`: Superseded.

`docs/WORKFLOWS.md`: Remains normative. Update to reference contract docs for matching/confidence behavior.

**Provider scope cleanup:**

**Step 2a: Import sweep** for all non-TIDAL/non-Beatport provider references: `apple_music`, `itunes`, `spotify`, `qobuz`, `musicbrainz`, `traxsource`, `deezer`. Include imports, CLI entrypoints, test fixtures, schema references, docs.

**Step 2b: Archive** all dropped provider files to `tagslut/legacy/dropped_providers_2026-03-19/` with README stating the architectural decision and date.

**Step 2c: Schema audit.** Check `track_identity` table and `identity_service.py` for columns or resolution paths referencing dropped providers. The only active provider columns should be `beatport_id` and `tidal_id`. Remove or mark deprecated any others.

**Step 2d: Legacy wrapper.** Deprecate `tagslut/metadata/models.py`. Update imports. Move to legacy if zero active imports.

**Step 2e: Shell scripts.** Verify harvest script status. Archive if dead.

**Step 2f: Test verification** after each move.

---

### Phase 3: Provider Alignment and Write-Path Audit

**Goals:** Resolve TIDAL transport ambiguity. Investigate Beatport ISRC endpoint. Define convergence interface. Audit all write paths against the Supabase transaction constraint.

**Prerequisite:** Phase 1 complete.

**3a: TIDAL transport audit.** Document in `tidal.py` which methods use v2 vs. v1 and why. v1 playlist export is legacy; no migration without parity validation.

**3b: TIDAL ISRC capability resolution.** Determine whether `search_by_isrc` equivalent uses v2 `filter[isrc]` or v1 text search. With two providers, this determines ISRC reliability for half the provider surface. Update contract doc.

**3c: Beatport auth boundary visibility.** Add log/warning on fallback to web-scraping. Update contract doc.

**3d: Beatport ISRC path endpoint.** Test `/v4/catalog/tracks/store/{isrc}/` with a known ISRC. Compare to query-parameter approach. If direct record without pagination, prefer it. High priority: Beatport ISRC quality is half the identity surface.

**3e: Confidence normalization.** Wire `MatchConfidence` enum into the identity service DB layer as canonical representation. Define mapping (e.g., EXACT=1.0, STRONG=0.85, MEDIUM=0.6, WEAK=0.4, NONE=0.0). CSV output derives numeric values from the enum, no longer hard-coded. Both paths store identical confidence for identical matches.

**3f: Convergence interface definition.** Document in `metadata_architecture.md`: the exact `resolve_or_create_identity()` parameters, return guarantees (idempotent, `identity_key` stable, provider data merge), same-track behavior (second write is merge or no-op, never conflict). With two providers, a `track_identity` row has at most one `beatport_id` and one `tidal_id`. Conflicting writes must be detected and rejected or logged. Specify which parameters each path provides and what the identity service normalizes.

**3g: Write-path atomicity audit.** This is the Supabase-specific phase. For every method in `identity_service.py` that writes to `track_identity` or related tables:

Classify as: (a) single-row PostgREST call (safe without wrapping), (b) multi-step operation currently chained client-side (unsafe, must be refactored), or (c) already wrapped in Postgres function / RPC (safe).

For any method classified as (b), determine whether to: wrap in a Postgres function (preferred for operations called frequently from both paths), or execute via direct psycopg connection with explicit transaction control (acceptable for rare administrative operations).

Specific operations to audit: `resolve_or_create_identity()` (resolution + insert/update is inherently multi-step), merge operations (`merged_into_id` repointing), identity status transitions, and any operation that writes to both `track_identity` and `asset_link` in a single logical unit.

Document findings in `metadata_architecture.md` under the Supabase transaction model section. For each critical write method, state: what it does, whether it is currently atomic, and what mechanism provides atomicity (Postgres function name, or "direct connection with BEGIN/COMMIT").

**Deliverable:** A write-path audit table in the contract doc listing every `identity_service` write method, its atomicity status, and its mechanism. Any method that is currently unsafe must have a migration plan before Phase 4 testing can be trusted.

---

### Phase 4: Test Hardening

**Goals:** Close testing gaps. Priority weighted toward identity service. Two-provider constraint simplifies the test matrix.

**Prerequisite:** Phases 1-3 complete (including write-path audit; tests are unreliable if writes are non-atomic).

**High priority (identity service core):**

**4a: Resolution path tests.** Full cascade: ISRC > `beatport_id` > `tidal_id` > fuzzy > no match. Assert path taken, `match_method`, `match_confidence` per contract. With two providers, enumerate all scenarios exhaustively.

**4b: Provenance safety.** Writing Beatport data must not overwrite existing TIDAL data, and vice versa. Two providers, two-way invariant.

**4c: Fuzzy threshold boundaries.** Duration 2.0s (match) vs. 2.01s (no match). Score 0.92 (match) vs. 0.919 (no match).

**4d: Convergence tests.** Same track through both paths, assert identical `track_identity` state. If batch CSV does not yet write to `identity_service`, design tests now; runnable when bridge is built.

**4e: Confidence normalization tests.** Enum-to-numeric consistent across both paths.

**4f: Atomicity tests.** For each write method classified in Phase 3g, test that a simulated mid-operation failure (e.g., injected exception between steps) does not leave the database in an inconsistent state. This is particularly important for `resolve_or_create_identity()` and merge operations. If a method is wrapped in a Postgres function, test that the function rolls back on error. If it uses a direct connection, test that the transaction aborts cleanly.

**Medium priority (provider infrastructure):**

**4g: Auth-absent Beatport degradation.** Simulate missing auth. Verify fallback and logging.

**4h: Edge cases.** Multi-candidate ISRC (2+ Beatport tracks for one ISRC; first-wins + logging). Title/artist ties (deterministic). Malformed input (skip + count). Two providers means small, exhaustive matrix.

**Lower priority (batch interface):**

**4i: Header stability regression.** Frozen tuples; changes fail tests. Verify dropped-provider columns removed.

---

### Phase 5: Bidirectional Enrichment

**Goals:** Implement Beatport-origin enrichment with TIDAL data.

**Prerequisite:** Phase 3 complete (TIDAL ISRC capability resolved, convergence interface defined, write-path audit done).

**5a: Implementation brief.** Spec for `enrich_beatport_seed_row` following the existing `enrich_tidal_seed_row` pattern. Key constraint: TIDAL has no native ISRC search endpoint. If Phase 3b confirms v2 `filter[isrc]` works, the reverse path can use it. Otherwise, the reverse path must use v2 text search with title/artist, which produces lower confidence matches.

**5b: Reverse seed CSV schema.** Define `BEATPORT_SEED_COLUMNS` and `BEATPORT_TIDAL_MERGED_COLUMNS` as fixed tuples in `types.py`. Add corresponding dataclasses. Align with the field mapping table in the CSV contract doc.

**5c: Write-path for reverse enrichment.** The reverse enrichment must use the same `resolve_or_create_identity()` convergence interface defined in Phase 3f and satisfy the same atomicity requirements from Phase 3g. No new write paths that bypass the identity service.

**5d: Tests.** Beatport-origin ISRC match (if TIDAL v2 filter works). Beatport-origin title/artist fallback. Beatport-origin no-match. Provenance safety (TIDAL enrichment does not overwrite Beatport seed data). Convergence (reverse-enriched track produces same identity state as if it had been ingested via intake).

---

### Phase 6: Governance

**Goals:** Prevent doc drift. Enforce convergence and atomicity guarantees.

`docs/contracts/README.md`: Contract docs are normative. Changes to identity resolution, CSV schemas, match precedence, confidence, or write-path atomicity require contract doc update in the same PR. Design docs in `docs/design/` are non-normative.

`docs/contracts/MAINTENANCE.md`: How to add a provider (not expected, but documented for completeness: schema change + identity service update + contract doc + tests + write-path audit). How to update CSV schemas (tuple + contract + tests + field mapping table). How to archive files. Convergence rule: any `identity_service` change verified against both paths. Write-path rule: any new write method must be classified per the Phase 3g audit and must satisfy the Supabase transaction constraint before merging.

Field mapping table in `metadata_row_contracts.md`: CSV column to identity service parameter to `track_identity` column.

CI or review checklist flagging PRs that touch `types.py`, `identity_service.py`, or provider files without contract doc update.

Optional: `--dry-run` flag on enrichment CLI.

---

## Section 4: Risks and Mitigations

**Risk 1: Token exposure from HAR/auth files.**
Severity: High. Mitigation: Phase 0 first.

**Risk 2: TIDAL v1 removal breaks playlist export.**
Severity: Medium. Mitigation: Phase 3a is audit, not migration. No v1 removal without parity validation.

**Risk 3: Beatport auth loss silently degrades pipeline.**
Severity: Medium. Mitigation: Phase 3c adds logging.

**Risk 4: Beatport ISRC path endpoint has different auth/rate-limit.**
Severity: Low-Medium. Mitigation: Small batch test before switching. Keep query-parameter as fallback.

**Risk 5: Archive moves break hidden imports.**
Severity: Low-Medium. Mitigation: Phase 2a sweep includes CLI entrypoints, shell scripts, Makefiles, docs.

**Risk 6: CSV schema change breaks downstream consumers.**
Severity: Unknown (depends on Q8 answer). Mitigation: Phase 1 freezes schema. Phase 4i adds regression.

**Risk 7: Fuzzy thresholds produce bad matches.**
Severity: Medium. Two providers amplifies impact. Mitigation: Phase 4c boundary tests. No changes without calibration data.

**Risk 8: Silent divergence between paths.**
Severity: High. Mitigation: Phase 4d convergence tests. Phase 6 governance. `identity_service` as sole writer.

**Risk 9: Non-atomic writes corrupt identity state.**
Severity: High. This is the Supabase-specific risk. If `resolve_or_create_identity()` or merge operations chain client-side PostgREST calls without transaction wrapping, a failure mid-operation leaves partial state: an identity row without its asset link, a merge with the old identity not fully repointed, a confidence value written but the match method not updated. Mitigation: Phase 3g audit identifies every unsafe method. Refactoring to Postgres functions or server-side transactions must be completed before Phase 4 tests can be trusted. Phase 4f atomicity tests verify that failures roll back cleanly.

**Risk 10: Provider reduction leaves orphaned schema artifacts.**
Severity: Low. Columns, indexes, or constraints referencing dropped providers may persist in the database or migrations. Mitigation: Phase 2c schema audit explicitly checks for these.

---

## Section 5: Remaining Open Items

All architectural questions are resolved. The following are operational items requiring owner action:

**O1: External CSV consumers (was Q8).** Still unknown. Must be identified before any CSV schema change. If none exist, CSV schema changes are safe after Phase 1 freeze.

**O2: Operator tooling audit (was Q9).** 12 files under `tools/review/` with unknown active/dead status. Owner must confirm before Phase 2 archive sweep.

**O3: Beatport `/v4/catalog/tracks/store/{isrc}/` testing (was Q7).** High priority. Needs a manual test with a known ISRC to compare response shape. This can be done independently of the phased plan and should be done early -- the result affects Phase 3d.

**O4: Batch CSV bridge to identity_service.** Does the batch CSV path currently write to `track_identity` via `identity_service`, or does it stop at CSV output? If it stops at CSV, convergence tests (Phase 4d) are designable now but not runnable until the bridge is built. If it writes, convergence is testable immediately.

---

## Appendix: Report Reconciliation Summary

### Where the reports agree

Both agree the v3 identity model is real and code-backed. Both agree `types.py` defines stable vendor seed and merged row dataclasses with fixed header tuples. Both agree identity service prioritizes ISRC > provider IDs > fuzzy. Both agree TIDAL provider is in hybrid v2/v1 state. Both agree metadata design docs are not reliable descriptions of current runtime behavior.

### Where the reports diverge

The public report is limited to GitHub surface with no operational recommendations. The local report adds operational context and cleanup recommendations. The public report treats tests as "evidence of what the repo is trying to preserve"; the local report treats them prescriptively.

### Specific factual tension

The Dual-Source doc states TidalProvider has "no dedicated ISRC endpoint" using "client-side filtering on text search results." The public report observes v2 `filter[isrc]` on `GET /tracks`. These describe different API surfaces (v1 vs. v2). Flagged in Issue 2 and Phase 3b.

### Findings from OAS inspection not in either report

Beatport v4 OAS contains `/v4/catalog/tracks/store/{isrc}/` as a dedicated path-based ISRC lookup, distinct from query-parameter filtering. Flagged in Issue 3 and Phase 3d.

### Changes since original reports

Provider scope reduced to TIDAL + Beatport only. TIDAL OAuth PKCE resolved. Supabase transaction constraint identified as architecturally load-bearing. These changes simplify the identity model, resolution logic, and merge semantics while introducing a new class of correctness concern (write-path atomicity).
