# Data Model Recommendation

## Hard recommendation

Keep one canonical SQLite database, but split the model into explicit master, MP3, and DJ layers. Do not keep using `files` as the catch-all store for DJ state.

## Current model problems

**Evidence**
- `tagslut/storage/schema.py` defines a broad `files` table and additive DJ-related columns.
- Migrations `0002`, `0003`, and `0008` add `dj_flag`, `dj_pool_path`, `rekordbox_id`, `last_exported_usb`, `dj_set_role`, `dj_subrole`, and gig-set tables.

**Why this is wrong**
- Master file state and DJ-export state change for different reasons.
- Derivative MP3 assets are not equivalent to master files.
- Rekordbox TrackID is not master-file metadata.

## Recommended schema partition

### Main/canonical tables

Keep and continue using:
- `asset_file`
- `track_identity`
- `asset_link`
- `provenance_event`
- move plan / execution tables
- canonical enrichment fields

These remain the root truth for masters.

### New derivative tables

```sql
CREATE TABLE mp3_asset (
  id INTEGER PRIMARY KEY,
  identity_id INTEGER NOT NULL,
  master_asset_id INTEGER NOT NULL,
  profile TEXT NOT NULL,
  path TEXT NOT NULL UNIQUE,
  sha256 TEXT,
  bitrate INTEGER,
  sample_rate INTEGER,
  status TEXT NOT NULL,
  transcoded_at TEXT,
  FOREIGN KEY(identity_id) REFERENCES track_identity(id),
  FOREIGN KEY(master_asset_id) REFERENCES asset_file(id)
);
```

### New DJ tables

```sql
CREATE TABLE dj_admission (
  id INTEGER PRIMARY KEY,
  identity_id INTEGER NOT NULL UNIQUE,
  preferred_mp3_asset_id INTEGER NOT NULL,
  status TEXT NOT NULL,
  admitted_at TEXT,
  notes_json TEXT,
  FOREIGN KEY(identity_id) REFERENCES track_identity(id),
  FOREIGN KEY(preferred_mp3_asset_id) REFERENCES mp3_asset(id)
);

CREATE TABLE dj_track_id_map (
  id INTEGER PRIMARY KEY,
  dj_admission_id INTEGER NOT NULL UNIQUE,
  rekordbox_track_id INTEGER NOT NULL UNIQUE,
  assigned_at TEXT,
  FOREIGN KEY(dj_admission_id) REFERENCES dj_admission(id)
);

CREATE TABLE dj_playlist (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  parent_id INTEGER,
  sort_key TEXT,
  UNIQUE(name, parent_id)
);

CREATE TABLE dj_playlist_track (
  playlist_id INTEGER NOT NULL,
  dj_admission_id INTEGER NOT NULL,
  ordinal INTEGER NOT NULL,
  PRIMARY KEY (playlist_id, dj_admission_id),
  FOREIGN KEY(playlist_id) REFERENCES dj_playlist(id),
  FOREIGN KEY(dj_admission_id) REFERENCES dj_admission(id)
);

CREATE TABLE dj_export_state (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL,
  output_path TEXT NOT NULL,
  manifest_hash TEXT,
  emitted_at TEXT,
  details_json TEXT
);
```

## Migration strategy

### Phase 1
- Introduce new tables with no behavior change.
- Mirror writes from new commands only.

### Phase 2
- Backfill `mp3_asset` from `files.dj_pool_path` where resolvable.
- Backfill `dj_track_id_map` from `files.rekordbox_id` where safe.
- Backfill `dj_admission` from existing DJ roots and export logic only after validation.

### Phase 3
- Mark `files.dj_pool_path` and `files.rekordbox_id` deprecated.
- Stop writing new authoritative DJ state there.

## What belongs where

| Concern | Store in canonical DB? | Store in `files`? | Store in new `mp3_*` / `dj_*` tables? |
|---|---|---|---|
| master FLAC provenance | yes | no if v3 table exists | canonical tables |
| enrichment | yes | compatibility mirror only if needed | canonical tables |
| MP3 derivative path/checksum/profile | yes | no | `mp3_asset` |
| DJ admission status | yes | no | `dj_admission` |
| Rekordbox TrackID | yes | no | `dj_track_id_map` |
| playlist membership | yes | no | `dj_playlist*` |
| XML export manifest | yes | no | `dj_export_state` |

## Delete, collapse, demote

- Demote `files.dj_pool_path`.
- Demote `files.rekordbox_id`.
- Treat `gig_sets` / `gig_set_tracks` as legacy until mapped into explicit playlist/export semantics.
- Collapse any operator workflow that still relies on path matching instead of identity-linked derivative/admission rows.
