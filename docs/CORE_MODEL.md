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
