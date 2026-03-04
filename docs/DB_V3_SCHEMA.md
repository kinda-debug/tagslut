# DB V3 Schema (Core)

This document summarizes the core v3 tables and ownership model.
Source of truth for table definitions: `tagslut/storage/schema.py` (`_ensure_v3_schema`).

## Core Tables

### `asset_file`
Authoritative physical record per file asset.

Key columns:
- `id` (PK)
- `path` (UNIQUE)
- `content_sha256`, `streaminfo_md5`, `checksum`
- `size_bytes`, `mtime`, `duration_s`, `sample_rate`, `bit_depth`, `bitrate`
- `library`, `zone`, `download_source`, `download_date`, `mgmt_status`
- `first_seen_at`, `last_seen_at`

Ownership:
- Physical facts only.
- Never canonical identity truth.

### `track_identity`
Authoritative canonical identity record.

Key columns:
- `id` (PK)
- `identity_key` (UNIQUE; e.g., `isrc:*`, `beatport:*`, `text:*`)
- `isrc`, `beatport_id`, `artist_norm`, `title_norm`
- `duration_ref_ms`, `ref_source`
- `created_at`, `updated_at`

Ownership:
- Canonical identity facts only.

### `asset_link`
Mapping between physical asset and canonical identity.

Key columns:
- `id` (PK)
- `asset_id` (FK -> `asset_file.id`)
- `identity_id` (FK -> `track_identity.id`)
- `confidence`, `link_source`, `active`
- `created_at`, `updated_at`
- unique pair: `(asset_id, identity_id)`

Ownership:
- Asset-to-identity binding.
- Operational contract: each asset has exactly one active link.

### `move_plan`
Move intent and policy context.

Key columns:
- `id` (PK)
- `plan_key` (UNIQUE)
- `plan_type`, `plan_path`, `policy_version`, `context_json`
- `created_at`

Ownership:
- Planned move metadata, not execution outcomes.

### `move_execution`
Recorded move attempts and outcomes.

Key columns:
- `id` (PK)
- `plan_id` (FK -> `move_plan.id`)
- `asset_id` (FK -> `asset_file.id`)
- `source_path`, `dest_path`, `action`, `status`
- `verification`, `error`, `details_json`
- `executed_at`

Ownership:
- Execution truth for move attempts.

### `provenance_event`
Immutable audit event stream linking assets, identities, plans, and executions.

Key columns:
- `id` (PK)
- `event_type`, `event_time`
- `asset_id`, `identity_id`, `move_plan_id`, `move_execution_id` (FKs)
- `source_path`, `dest_path`, `status`, `details_json`

Ownership:
- Chronological audit trail.

## Optional vs Core

DJ-focused tables/flows (for example `gig_sets`, `gig_set_tracks`, DJ export state) are optional.
Core indexing, identity linking, moves, and audit must work without DJ workflows.

## Forbidden Patterns

1. Identity inference from filenames/paths as authoritative input.
2. Path truth stored outside `asset_file` + move receipt/event trail.
3. Direct DB path rewrites without corresponding successful `move_execution`.
4. Requiring DJ state to validate core library integrity.

