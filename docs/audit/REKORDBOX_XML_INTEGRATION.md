# Rekordbox XML Integration

## Decision

Rekordbox XML should become a **formal first-class interoperability layer** for DJ export/import boundaries in this repo.

It should be:
- **primary DJ interoperability layer externally**
- **not** the primary internal source of truth
- **thin projection from DB state**, plus controlled patch support

## Why this decision fits the repo evidence

- The repo already contains Rekordbox-related modules under `tagslut/adapters/rekordbox/` and `tagslut/dj/rekordbox_prep.py`.
- `tagslut/cli/commands/dj.py` exposes `prep-rekordbox`, proving XML/prep interoperability matters operationally.
- The current model stores `rekordbox_id` directly on `files`, which is the wrong place if XML is meant to be stable and rebuild-safe.

## Hard recommendations

### 1. TrackID mapping

TrackID mapping should live in the DB DJ layer, not in XML alone and not on `files`.

Recommended store:
- `dj_track_id_map`
- or `dj_admission.rekordbox_track_id` if kept simple

### 2. Playlist membership projection

Playlist membership should live in DB tables and project to XML deterministically.

Recommended source tables:
- `dj_playlist`
- `dj_playlist_track`

XML should be emitted from these tables with stable ordering.

### 3. Retroactive MP3 admission into XML-facing flows

Retroactive flow must be:
1. `mp3 reconcile`
2. `dj admit` or `dj backfill`
3. `dj validate`
4. `dj xml emit` or `dj xml patch`

Do not use manual XML editing as the primary way to admit tracks.

### 4. Mandatory validations before XML emit/patch

- admitted track has one preferred MP3 asset
- MP3 file exists
- title and artist metadata are non-empty
- TrackID exists and is unique
- no duplicate emitted path under different TrackIDs
- playlist memberships only reference admitted tracks
- emitted XML ordering is deterministic
- patch target matches a known prior export manifest

### 5. Deterministic, reversible, rebuild-safe projection

Required properties:
- same DB state -> same logical XML output
- stable TrackIDs across rebuilds
- stable playlist ordering
- stored export manifest/hash
- reversible mapping from XML track entry back to `dj_admission` and `mp3_asset`
- full rebuild possible without hand-edited hidden state

## Proposed command behavior

### `tagslut dj xml emit`

**Purpose**
- Emit full Rekordbox XML from DJ DB state.

**Inputs**
- output path
- optional playlist scope
- optional profile

**Outputs**
- XML file
- export manifest row

**Source of truth**
- `dj_admission`, `dj_track_id_map`, `dj_playlist*`, `mp3_asset`

**Mutates**
- XML + DB export-state

### `tagslut dj xml patch`

**Purpose**
- Patch a previously emitted XML deterministically from changed DJ DB state.

**Inputs**
- prior export id or xml path
- scope / changed playlists / changed track ids

**Outputs**
- patched XML
- patch manifest row

**Source of truth**
- same as above plus prior export state

**Mutates**
- XML + DB export-state

## What the current repo should stop doing

- Stop treating `prep-rekordbox` as enough of an architecture.
- Stop treating `files.rekordbox_id` as the durable source of TrackID truth.
- Stop allowing path-derived ad hoc DJ state to stand in for formal XML projection input.
