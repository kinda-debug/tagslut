# Metadata Architecture Contract

**Status:** Normative  
**Anchored to:** commit `a060a2b` + local repo state 2026-03-19  
**Supersedes:** `metadata.md`, `Dual-SourceTIDALBeatportMetadataFlow.md`

---

## Provider Scope

Strictly dual-provider: **TIDAL** and **Beatport** only.

All other providers (Apple Music, iTunes, Spotify, Qobuz, MusicBrainz, Traxsource, Deezer) are explicitly out of scope. They are not used for identity resolution, uniqueness enforcement, or merge logic. This is an architectural decision, not a temporary reduction.

Only two authoritative provider identifiers exist: `beatport_id` and `tidal_id`.

---

## Canonical Store

`track_identity` is the canonical store for all resolved track metadata.

`identity_service` (`tagslut/storage/v3/identity_service.py`) is the **sole writer** to `track_identity`. Any path that writes to `track_identity` without going through `identity_service` is invalid.

---

## Identity Key Derivation

Deterministic, no cross-provider ambiguity:

1. **ISRC** (when trusted): `isrc:{isrc.lower()}`
2. **Beatport ID**: `beatport:{beatport_id}`
3. **TIDAL ID**: `tidal:{tidal_id}`
4. **Fuzzy artist/title**: `text:{artist_norm}|{title_norm}`
5. **Unidentified**: `unidentified:asset:{id}` or `unidentified:path:{path}`

---

## `resolve_or_create_identity()` Behavior

**Signature:** `resolve_or_create_identity(conn, asset_row, metadata, provenance) -> int`

**Resolution order:**
1. Existing active asset link for this asset_id
2. ISRC match in `track_identity`
3. Provider ID match (`beatport_id`, then `tidal_id`)
4. Fuzzy artist/title/duration match
5. Create new identity

**Guarantees:**
- Idempotent: calling twice with identical input returns the same identity_id
- `identity_key` is stable once assigned
- On match: merges non-empty fields into existing row (fill-empty semantics, never overwrites)
- On create: inserts new row with derived `identity_key`
- Atomic: wraps in `BEGIN IMMEDIATE` / `COMMIT` / `ROLLBACK` when not already in a transaction

**Hard invariant:** `identity_service` is the sole writer. Bypass is invalid.

---

## Convergence Guarantee

Both ingestion paths must produce identical `track_identity` state for identical input:

- **Path A (intake):** `tagslut intake` → providers → `resolve_or_create_identity()` directly
- **Path B (batch CSV):** TIDAL playlist export → seed CSV → Beatport enrichment → merged CSV → *(bridge to identity_service: not yet implemented — see Open Items)*

When the batch CSV bridge is built, it must use the same `resolve_or_create_identity()` interface. No new write paths that bypass the identity service.

---

## Confidence Normalization

`MatchConfidence` enum is the canonical representation. Numeric values derive from the enum via `CONFIDENCE_NUMERIC` mapping (defined in `tagslut/metadata/models/types.py`):

| Enum | Numeric |
|------|---------|
| EXACT | 1.0 |
| STRONG | 0.85 |
| MEDIUM | 0.70 |
| WEAK | 0.55 |
| NONE | 0.0 |

CSV output serializes the enum to float using this mapping. The DB stores the enum value (string). Hard-coded numeric values in provider code are invalid after Phase 3e implementation.

---

## Fuzzy Match Thresholds

| Parameter | Value | Status |
|-----------|-------|--------|
| `FUZZY_DURATION_TOLERANCE_S` | 2.0s | Uncalibrated |
| `FUZZY_SCORE_THRESHOLD` | 0.92 | Uncalibrated |

These values have not been calibrated against real data. Do not change without calibration evidence.

---

## Supabase Transaction Model

The system runs on Supabase (Postgres via PostgREST). Client-side multi-step transactions are not supported via PostgREST. Complex atomic operations must use either:
- **Postgres functions (RPC):** preferred for operations called frequently from both paths
- **Direct psycopg connection with explicit `BEGIN`/`COMMIT`:** acceptable for rare administrative operations

### Write-Path Atomicity Audit

*(Phase 3g — to be completed)*

| Method | Operation | Currently Atomic? | Mechanism |
|--------|-----------|-------------------|-----------|
| `resolve_or_create_identity()` | Resolution + insert/update | Yes (SQLite: BEGIN IMMEDIATE) | Needs audit for Supabase/PostgREST path |
| `link_asset_to_identity()` | Insert/update asset_link | Single-row or two-step | Needs audit |
| `_merge_identity_fields_if_empty()` | SELECT + conditional UPDATE | Two-step, not wrapped | Needs audit |
| `mirror_identity_to_legacy()` | UPDATE files + INSERT library_tracks | Two separate statements | Needs audit |
| merge operations (`merge_identities.py`) | Repoint merged_into_id | Multi-step | Needs audit |

**Status:** SQLite path uses `BEGIN IMMEDIATE` in `resolve_or_create_identity()`. Supabase/PostgREST path atomicity is unverified. Phase 3g must classify each method and specify the mechanism before Phase 4 tests can be trusted.

---

## Open Items

**O4: Batch CSV bridge to identity_service.** Does the batch CSV path currently write to `track_identity` via `identity_service`, or does it stop at CSV output? If it stops at CSV, convergence tests (Phase 4d) are designable now but not runnable until the bridge is built.
