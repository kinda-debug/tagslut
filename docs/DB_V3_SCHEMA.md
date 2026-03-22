<!-- Status: Active document. Synced 2026-03-22 after migration 0012 (ingestion provenance). Historical or superseded material belongs in docs/archive/. -->

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
- Ingestion provenance (NOT NULL, migration 0012): `ingested_at`, `ingestion_method`, `ingestion_source`, `ingestion_confidence`
- Merge / lifecycle: `merged_into_id`, `created_at`, `updated_at`

`canonical_payload_json` extended keys (Lexicon backfill, 2026-03-14):
- `lexicon_track_id` — Lexicon DB primary key for this track
- `lexicon_energy`, `lexicon_danceability`, `lexicon_happiness`, `lexicon_popularity` — Lexicon 1-10 scores
- `lexicon_bpm` — only written if `canonical_bpm` is NULL
- `lexicon_key` — only written if `canonical_key` is NULL
Access via `json_extract(canonical_payload_json, '$.lexicon_energy')` etc.
Source module: `tagslut/dj/reconcile/lexicon_backfill.py`.

Ownership:
- Canonical identity facts only.

Identity-hardening status:

- Active-only uniqueness is enforced for exactly seven provider ids (`beatport_id`, `tidal_id`, `qobuz_id`, `spotify_id`, `apple_music_id`, `deezer_id`, `traxsource_id`); see `docs/architecture/V3_IDENTITY_HARDENING.md`.
- `itunes_id` and `musicbrainz_id` are helper-level identifiers only (lookup/identity key derivation, not schema-enforced uniqueness); see `docs/architecture/V3_IDENTITY_HARDENING.md`.
- Routine proof surface: `make check-v3-identity-integrity` (tests + schema-equivalence proof); see `docs/testing/V3_IDENTITY_HARDENING.md`.

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

## DJ Pipeline Tables (migration 0010)

These tables power the explicit 4-stage DJ pipeline (register → admit → emit → patch).
Applied via `tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql`.
Migration 0009 (`0009_add_mp3_dj_tables.sql`) defined earlier stubs for the same table names
but was superseded before being applied; 0010 is the authoritative DDL for all DJ pipeline tables.
Verification checkpoint: `data/checkpoints/reconcile_schema_0010.json`.

### `mp3_asset`
One row per registered MP3 derivative asset. May exist without a canonical `identity_id`
for legacy imports; `content_sha256` is the primary integrity anchor.

Key columns:
- `id` (PK, AUTOINCREMENT)
- `identity_id` (FK -> `track_identity.id`, nullable)
- `asset_id` (FK -> `asset_file.id`, nullable — master FLAC source)
- `path` (NOT NULL UNIQUE)
- `content_sha256`, `size_bytes`, `bitrate`, `sample_rate`, `duration_s`
- `profile` (DEFAULT `standard`)
- `status` CHECK (`unverified` | `verified` | `missing` | `superseded`), DEFAULT `unverified`
- `source` (DEFAULT `unknown`), `zone`
- `transcoded_at`, `reconciled_at`
- `lexicon_track_id` (Lexicon cross-reference, nullable)
- `created_at`, `updated_at`

Indexes: `identity_id`, `zone`, `lexicon_track_id`.

Ownership: all DJ MP3 derivatives live here, not in `files` or `asset_file`.

### `dj_admission`
Curated DJ library membership — one row per `track_identity` admitted to the live DJ library.

Key columns:
- `id` (PK, AUTOINCREMENT)
- `identity_id` (UNIQUE FK -> `track_identity.id`, nullable)
- `mp3_asset_id` (FK -> `mp3_asset.id`, nullable — preferred MP3 for this admission)
- `status` CHECK (`pending` | `admitted` | `rejected` | `needs_review`), DEFAULT `pending`
- `source` (DEFAULT `unknown`), `notes`
- `admitted_at`, `created_at`, `updated_at`

Index: `identity_id`.

Ownership: one active row per identity in the DJ library.

### `dj_track_id_map`
Stable Rekordbox TrackID assignments — decoupled from admission so IDs survive re-admission
or asset swaps.

Key columns:
- `id` (PK, AUTOINCREMENT)
- `dj_admission_id` (UNIQUE FK -> `dj_admission.id`)
- `rekordbox_track_id` (INTEGER NOT NULL UNIQUE, assigned sequentially, never reassigned)
- `assigned_at` (DEFAULT CURRENT_TIMESTAMP)

Invariant: once assigned, `rekordbox_track_id` is never changed for the same `dj_admission_id`.
This ensures Rekordbox cue points survive XML re-imports.

### `dj_playlist`
Hierarchical playlist tree mirroring the Rekordbox folder/playlist layout.

Key columns:
- `id` (PK, AUTOINCREMENT)
- `name` (NOT NULL), `parent_id` (self-FK -> `dj_playlist.id`, nullable for root nodes)
- `lexicon_playlist_id` (Lexicon cross-reference, nullable)
- `sort_key`, `playlist_type` (DEFAULT `standard`)
- `created_at`
- UNIQUE `(name, parent_id)`

### `dj_playlist_track`
Ordered track membership within a DJ playlist.

Key columns:
- `playlist_id` (NOT NULL FK -> `dj_playlist.id`)
- `dj_admission_id` (NOT NULL FK -> `dj_admission.id`)
- `ordinal` (NOT NULL — sort order within playlist)
- PRIMARY KEY `(playlist_id, dj_admission_id)`

### `dj_export_state`
One row per XML/NML/M3U emit — enables diff computation and tamper detection on re-export.

Key columns:
- `id` (PK, AUTOINCREMENT)
- `kind` (NOT NULL — e.g. `rekordbox_xml`)
- `output_path` (NOT NULL), `manifest_hash` (SHA-256 of emitted file)
- `scope_json` (serialised filter/scope used for this emit)
- `emitted_at` (DEFAULT CURRENT_TIMESTAMP)

Invariant: `patch_rekordbox_xml()` verifies that the on-disk file at `output_path`
matches `manifest_hash` before re-emitting. Mismatch raises `ValueError` loudly.

### `reconcile_log`
Append-only log of every reconciliation decision: file→identity linking, confidence scoring,
manual overrides. Never updated in-place; always inserted.

Key columns:
- `id` (PK, AUTOINCREMENT)
- `run_id` (NOT NULL — groups all events from a single reconcile run)
- `event_time` (DEFAULT CURRENT_TIMESTAMP)
- `source` (NOT NULL — e.g. `mp3_reconcile`, `manual`, `lexicondj`)
- `action` (NOT NULL — e.g. `linked`, `skipped`, `conflict`, `backfill_metadata`, `backfill_tempomarkers`)
- `confidence` (e.g. `isrc_exact`, `title_artist_fuzzy`, `high`, `medium`, `low`)
- `mp3_path`, `identity_id`, `lexicon_track_id`
- `details_json` (arbitrary structured payload)

Indexes: `run_id`, `identity_id`.

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

Note: `files.dj_set_role` on the flat `files` table is a separate downstream export field with values `groove | prime | bridge | club`. It is not the same field as `dj_track_profile.set_role`, which is an identity-layer v3 curation overlay with values `warmup | builder | peak | tool | closer | ambient | break | unknown`.

## Forbidden Patterns

1. Identity inference from filenames/paths as authoritative input.
2. Path truth stored outside `asset_file` + move receipt/event trail.
3. Direct DB path rewrites without corresponding successful `move_execution`.
4. Requiring DJ state to validate core library integrity.

---

## Ingestion Provenance Columns (migration 0012)

Four NOT NULL columns added to `track_identity`:

| Column | Type | Notes |
|---|---|---|
| `ingested_at` | TEXT (ISO 8601 UTC) | Set once at insert, never updated |
| `ingestion_method` | TEXT | Controlled vocabulary (see below) |
| `ingestion_source` | TEXT | Specific evidence e.g. `beatport_api:track_id=12345678` |
| `ingestion_confidence` | TEXT | Five-tier vocabulary (see below) |

Enforcement:
- SQLite insert trigger: `trg_track_identity_provenance_required`
- Behavior: rejects INSERTs where `ingested_at`, `ingestion_method`, or `ingestion_confidence`
  are NULL/blank, or where `ingestion_source` is NULL
- Legacy `init_db()` additive migration path creates the same trigger for databases that do not
  originate from `create_schema_v3()`

`ingestion_confidence` vocabulary:

| Tier | Meaning |
|---|---|
| `verified` | Directly confirmed from authoritative provider evidence |
| `corroborated` | Confirmed by multiple consistent provider signals |
| `high` | Strong single-source or rule-based confidence |
| `uncertain` | Identity retained but evidence is conflicting or incomplete |
| `legacy` | Backfilled historical row where original ingestion evidence is unavailable |

`ingestion_method` vocabulary:

| Method | Meaning |
|---|---|
| `provider_api` | Direct provider/API metadata ingest |
| `isrc_lookup` | Identity created from ISRC resolution |
| `fingerprint_match` | Identity created from acoustic fingerprint matching |
| `fuzzy_text_match` | Identity created from normalized text similarity |
| `picard_tag` | Identity derived from Picard / MusicBrainz tagging |
| `manual` | Operator-created or operator-confirmed row |
| `migration` | Backfilled during schema/data migration |
| `multi_provider_reconcile` | Created or hardened during multi-provider reconciliation |

References: `docs/INGESTION_PROVENANCE.md`, `docs/MULTI_PROVIDER_ID_POLICY.md`

---

## Provider ID Conflict JSON (canonical_payload_json keys)

When Track B (multi-provider reconcile) detects a provider ID that resolves
to a different ISRC than the canonical ISRC, the conflict is recorded in
`canonical_payload_json` under these keys:

```json
{
  "provider_id_conflicts": [
    {
      "provider": "spotify_id",
      "stored_value": "4abc123",
      "resolved_isrc": "GBUM71505512",
      "canonical_isrc": "USQX91501234",
      "detected_at": "2026-03-21T14:00:00Z"
    }
  ],
  "provider_id_conflicts_resolved": [
    {
      "provider": "spotify_id",
      "stored_value": "4abc123",
      "resolution": "confirmed canonical ISRC correct — spotify pointed to different track",
      "resolved_at": "2026-03-22T10:00:00Z"
    }
  ]
}
```

Any row with a non-empty `provider_id_conflicts` array must have
`ingestion_confidence = 'uncertain'` regardless of other corroboration.
Resolution requires operator review. After resolution, entry moves to
`provider_id_conflicts_resolved` with timestamp and note.
