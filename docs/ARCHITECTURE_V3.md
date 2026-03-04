# Architecture V3

Authoritative v3 architecture reference.

## Data Model
- `asset_file`: physical asset truth (path, checks, technical metadata).
- `track_identity`: logical identity truth (keys, provider IDs, canonical metadata).
- `asset_link`: deterministic mapping from asset to identity (one link per asset).
- `preferred_asset`: one materialized preferred asset per active identity.
- `identity_status`: lifecycle status rows for non-merged identities.

## Identity Lifecycle
- `active`: non-merged identity with one or more linked assets.
- `orphan`: non-merged identity with zero linked assets.
- `archived`: non-merged identity intentionally excluded from normal workflows.
- `merged`: tombstoned identity (`merged_into_id IS NOT NULL`), excluded from lifecycle recompute.

## Promotion Pipeline
1. `register`
2. `integrity`
3. `identify`
4. `enrich`
5. `art`
6. `promote`
7. `dj`

## Safety Gates
- `doctor`: v3 schema and invariant checks.
- invariant checks: post-promote preferred-asset selection verification.
- merge verification: duplicate-key merge plan/execute validation and post-merge QA.
