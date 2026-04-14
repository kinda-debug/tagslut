# P5 — Final Audit and Rekordbox Export Setup

## Purpose
After P1–P4: verify no audio files remain in unresolved/staging locations,
generate a clean state report, and produce a Rekordbox-importable XML from
the DB for the DJ pool.

## Prerequisites
P1–P4 must have run. All TSV reports from previous prompts must exist in
`/Volumes/MUSIC/logs/`.

## Do not recreate existing files. Do not run the full test suite.

---

## Part A — Final audit script (`tools/final_audit.py`)

Re-scan all locations from P1. For each location, report:
- Files remaining (should be zero for staging and _UNRESOLVED locations
  after P2–P4)
- Files still not in DB
- Files with no ISRC

Write to `/Volumes/MUSIC/logs/final_audit_YYYYMMDD_HHMMSS.tsv` (same
columns as P1 inventory TSV).

Print a clean summary per location:
```
staging_spotiflacnext:  N files remaining  (N not in DB, N no ISRC)
staging_spotiflac:      ...
master_unresolved:      ...
master_unresolved_from_library: ...
mp3_library_spotiflac_next: ...
mp3_leftovers:          ...
```

If any staging or _UNRESOLVED location has files remaining, print:
```
WARNING: N files remain unaccounted for. Review logs before proceeding.
```

## Part B — Rekordbox XML export (`tools/rekordbox_export.py`)

Generate a Rekordbox-importable XML from the DB. This replaces the
existing XML files on `/Volumes/MUSIC/`.

**Source:** `mp3_asset` joined with `track_identity` joined with
`asset_file` where `mp3_asset.zone = 'MP3_LIBRARY'`.

**XML format:** Rekordbox DJ library XML (same schema as existing
`/Volumes/MUSIC/rekordbox_mp3.xml` — read that file first to confirm
the exact schema before writing).

**Fields to populate per track:**
- `TrackID`: `mp3_asset.id`
- `Name`: `track_identity.title_norm` (or tag title if available)
- `Artist`: `track_identity.artist_norm`
- `Album`: from tag hoard or empty
- `TotalTime`: `mp3_asset.duration_s` as integer seconds
- `BitRate`: `mp3_asset.bitrate`
- `SampleRate`: `mp3_asset.sample_rate`
- `Location`: `file://localhost` + URL-encoded `mp3_asset.path`
- `DateAdded`: `mp3_asset.created_at` as YYYY-MM-DD

**Output:** `/Volumes/MUSIC/rekordbox_fresh_YYYYMMDD.xml`

Do not overwrite any existing XML file. Always write a new timestamped file.

## Script entrypoints

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/final_audit.py
poetry run python3 tools/rekordbox_export.py
```

## Acceptance

Both scripts run to completion without errors. Final audit TSV written.
Rekordbox XML written and is valid XML (run `xmllint --noout` on it).
Print:
```
Final audit: N total files across all locations, N unaccounted
Rekordbox XML: N tracks written to /Volumes/MUSIC/rekordbox_fresh_YYYYMMDD.xml
```

## Commit

```
feat(tools): add final_audit.py and rekordbox_export.py for library closeout
```
