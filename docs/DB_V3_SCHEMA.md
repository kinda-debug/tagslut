<!-- Status: Active document. Synced 2026-03-09 after recent code/doc review. Historical or superseded material belongs in docs/archive/. -->

# DB V3 Schema (Core)

This document summarizes the core v3 tables and ownership model.
Source of truth for v3 table definitions: `tagslut/storage/v3/schema.py` (`create_schema_v3`).

## Core Tables

### `asset_file`
Authoritative physical record per file asset.

Key columns:
- `id` (PK)
- `path` (UNIQUE)
- `content_sha256`, `streaminfo_md5`, `checksum`
- `size_bytes`, `mtime`, `duration_s`, `sample_rate`, `bit_depth`, `bitrate`
- `duration_measured_ms` (INTEGER)
- `library`, `zone`, `download_source`, `download_date`, `mgmt_status`
- `flac_ok` (INTEGER, boolean)
- `integrity_state` (TEXT, indexed)
- `integrity_checked_at` (TEXT, ISO timestamp)
- `sha256_checked_at` (TEXT)
- `streaminfo_checked_at` (TEXT)
- `first_seen_at`, `last_seen_at`

Ownership:
- Physical facts only.
- Never canonical identity truth.

### `track_identity`
Authoritative canonical identity record.

Key columns:
- `id` (PK)
- Identity key fields: `identity_key`, `isrc`, `beatport_id`, `tidal_id`, `qobuz_id`, `spotify_id`, `apple_music_id`, `deezer_id`, `traxsource_id`, `itunes_id`, `musicbrainz_id`
- Normalized search fields: `artist_norm`, `title_norm`, `album_norm`
- Canonical metadata fields: `canonical_title`, `canonical_artist`, `canonical_album`, `canonical_genre`, `canonical_sub_genre`, `canonical_label`, `canonical_catalog_number`, `canonical_mix_name`, `canonical_duration`, `canonical_year`, `canonical_release_date`, `canonical_bpm`, `canonical_key`, `canonical_payload_json`
- Enrichment / timing: `enriched_at`, `duration_ref_ms`, `ref_source`
- Merge / lifecycle: `merged_into_id`, `created_at`, `updated_at`

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
- unique on `asset_id` alone (`UNIQUE(asset_id)`); each asset has at most one link row at any time.

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

### `library_track_sources`
Provider/source snapshots linked to a canonical identity.

Key columns:
- `id` (PK)
- `identity_key` (FK -> `track_identity.identity_key`)
- `provider`, `provider_track_id`
- unique triplet: (`identity_key`, `provider`, `provider_track_id`)

### `identity_merge_log`
Audit log of merge decisions and outcomes.

Key columns:
- `id` (PK)
- `winner_identity_id` (FK -> `track_identity.id`)
- `merge_type`, `key_value`, `loser_identity_ids`
- `assets_moved`, `dry_run`

### `preferred_asset`
One deterministic preferred asset per identity.

Key columns:
- `identity_id` (PK, FK -> `track_identity.id`)
- `asset_id` (FK -> `asset_file.id`)
- `score`, `version`

### `identity_status`
Lifecycle/status record for an identity.

Key columns:
- `identity_id` (PK, FK -> `track_identity.id`)
- `status` (CHECK: `active`, `orphan`, `archived`)
- `version`

### `dj_track_profile`
DJ-curation overlay per identity.

Key columns:
- `identity_id` (PK, FK -> `track_identity.id`)
- `rating` (CHECK: `0..5`)
- `energy` (CHECK: `0..10`)
- `set_role` (CHECK: `warmup`, `builder`, `peak`, `tool`, `closer`, `ambient`, `break`, `unknown`)

### `scan_runs`
Top-level scan job records.

Key columns:
- `id` (PK)
- `mode` (CHECK: `queue`)
- `status`

### `scan_queue`
Per-path work items within a scan run.

Key columns:
- `id` (PK)
- `run_id` (FK -> `scan_runs.id`)
- `path`
- unique pair: (`run_id`, `path`)

### `scan_issues`
Issues discovered during scan processing.

Key columns:
- `id` (PK)
- `run_id` (FK -> `scan_runs.id`)
- `queue_id` (FK -> `scan_queue.id`, nullable)
- `issue_code`, `severity`

### `schema_migrations`
Applied v3 schema version markers.

Key columns:
- `id` (PK)
- `schema_name`, `version`
- unique pair: (`schema_name`, `version`)

## Views

### `v_active_identity`
Active non-merged identities only.

Key columns:
- Projects `track_identity` rows only
- Filter semantics: `merged_into_id IS NULL` and `identity_status.status = 'active'`

### `v_dj_ready_candidates`
DJ-ready identity projection with preferred asset and DJ profile overlays.

Key columns:
- `identity_id`, `identity_key`
- `preferred_asset_id`, `preferred_path`
- `status`, `rating`, `energy`, `set_role`
- Filter semantics: non-merged identities only

### `v_dj_pool_candidates_v3`
Wide DJ-pool candidate projection over identity, preferred asset, asset file, status, and DJ profile.

Key columns:
- `identity_id`, `identity_key`
- `preferred_asset_id`, `asset_path`
- `identity_status`, `merged_into_id`
- `dj_rating`, `dj_energy`, `dj_set_role`
- Filter semantics: non-merged identities only

### `v_dj_pool_candidates_active_v3`
DJ-pool candidates restricted to active identities with a preferred asset.

Key columns:
- Projects rows from `v_dj_pool_candidates_v3`
- Filter semantics: `preferred_asset_id IS NOT NULL` and `identity_status = 'active'`

### `v_dj_pool_candidates_active_orphan_v3`
DJ-pool candidates including active and orphan identities with a preferred asset.

Key columns:
- Projects rows from `v_dj_pool_candidates_v3`
- Filter semantics: `preferred_asset_id IS NOT NULL` and `identity_status IN ('active', 'orphan')`

## Optional vs Core

DJ-focused tables/flows (for example `gig_sets`, `gig_set_tracks`, DJ export state) are optional.
Core indexing, identity linking, moves, and audit must work without DJ workflows.

## Forbidden Patterns

1. Identity inference from filenames/paths as authoritative input.
2. Path truth stored outside `asset_file` + move receipt/event trail.
3. Direct DB path rewrites without corresponding successful `move_execution`.
4. Requiring DJ state to validate core library integrity.
