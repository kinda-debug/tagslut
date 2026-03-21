<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# Core Model (V3)

This is the canonical conceptual model for core library operations.

## Ownership of Facts

| Fact category | Authoritative owner | Stored in |
|---|---|---|
| Physical file facts (path, hashes, size, mtime, audio format facts, zone/library placement) | `asset_file` | `asset_file` |
| Canonical identity facts (ISRC/Beatport/text identity key, normalized artist/title, duration reference) | `track_identity` | `track_identity` |
| Asset-to-identity binding | `asset_link` | `asset_link` |
| Planned move intent/policy context | `move_plan` | `move_plan` |
| Executed move outcomes (success/failure, verification, errors) | `move_execution` | `move_execution` |
| Immutable audit trail across registration, linking, and moves | `provenance_event` | `provenance_event` |

## Core Rules

1. `asset_file` is authoritative for physical truth.
2. `track_identity` is authoritative for canonical identity truth.
3. Every asset has at most one `asset_link` row. The `active` column (default 1) is used for soft-delink; it does not represent historical alternatives. Use `UPDATE SET active=0` to delink without deleting.
4. `move_plan` + `move_execution` + `provenance_event` are authoritative for move/audit truth.
5. DJ workflows are optional overlays and must not be required for core library correctness.

## Forbidden

1. Do not infer identity from filenames, directory names, or path patterns.
2. Do not mutate canonical identity fields in `asset_file`.
3. Do not treat DJ-only fields/workflows as prerequisites for indexing, linking, moving, or auditing.
4. Do not update physical file path state without a corresponding successful move execution record.
5. Do not treat ad-hoc logs as authoritative when DB receipt/event tables disagree.

## Practical Implication

If facts conflict:
- physical facts come from `asset_file` + successful move receipts/events
- identity facts come from `track_identity`
- mapping truth comes from the active `asset_link`

## Ingestion Provenance (added 2026-03-21)

Every `track_identity` row has four mandatory provenance fields:

| Field | Type | Purpose |
|---|---|---|
| `ingested_at` | TEXT (ISO 8601 UTC) | When the row first entered the system. Set once, never updated. |
| `ingestion_method` | TEXT | How the identity was established. Controlled vocabulary. |
| `ingestion_source` | TEXT | Specific evidence (e.g. `beatport_api:track_id=12345678`). |
| `ingestion_confidence` | TEXT | Trust tier: `verified`, `high`, `uncertain`, `legacy`. |

These are NOT NULL. Any insert without them fails at the schema level.

Full specification: `docs/INGESTION_PROVENANCE.md`.

**Rule 6:** Do not treat `uncertain` or `legacy` tracks as verified
identities for DJ export, canonical tag writeback, or cross-provider
resolution without explicit operator review.

**Rule 7:** `ingested_at` is the indelible timestamp of origin.
It must never be updated, even on merge. Merges are recorded in
`provenance_event` with their own timestamp.
