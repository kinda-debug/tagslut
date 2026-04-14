# P6 — Promote Staging Originals to MASTER_LIBRARY

## Do not recreate existing files. Do not run the full test suite.

---

## Context

410 files remain in `staging/SpotiFLACnext`. These are lossless originals
(FLAC and M4A) that were downloaded and indexed in the DB as zone=`staging`
but never promoted to MASTER_LIBRARY. Until they are promoted, the 450+
orphan MP3s in `mp3_leftovers` and `mp3_library_spotiflac_next` cannot be
matched by P4 (no master FLAC to link against).

MP3 files in staging are derivatives — they do NOT get promoted to
MASTER_LIBRARY. Only FLAC and M4A originals are promoted.

---

## What "promote" means

For each `.flac` or `.m4a` in `staging/SpotiFLACnext`:

1. Read ISRC from embedded tags.
2. Look up `track_identity` by ISRC.
3. Derive target path in MASTER_LIBRARY using the same template as
   `resolve_unresolved.py`:
   `MASTER_LIBRARY/{artist}/({year}) {album}/{disc}-{track:02d}. {title} - {artist}.{ext}`
   Use file tags as fallback for any missing `track_identity` field.
   Use `0000` if year is empty.
4. Safety checks: target must not exist on disk; no existing `asset_file`
   row for target path.
5. Move the file.
6. Update `asset_file`: set `zone='MASTER_LIBRARY'`, `path=target`.
   Do NOT insert a new row — update the existing staging row.

---

## Write `tools/promote_staging.py`

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/promote_staging.py [--dry-run]
```

Scan: `FLAC` and `M4A` files only under `/Volumes/MUSIC/staging/SpotiFLACnext`.
Skip `.mp3` files entirely.

Report to `/Volumes/MUSIC/logs/promote_staging_YYYYMMDD_HHMMSS.tsv`:
```
source_path  result  target_path  isrc  identity_id  notes
```

`result` values: `promoted`, `no_isrc`, `isrc_not_found`, `duplicate_on_disk`,
`missing_required_fields`, `error`

Print summary:
```
Total originals: N
Promoted: N  |  No ISRC: N  |  ISRC not found: N  |  Duplicate: N  |  Errors: N
```

---

## After running promote_staging.py

Re-run P4:
```
poetry run python3 tools/mp3_consolidation.py
```

The `no_master_flac` count should drop significantly as the promoted FLACs
are now in MASTER_LIBRARY and linkable.

---

## Commit

```
feat(tools): add promote_staging.py to move SpotiFLACnext originals to MASTER_LIBRARY
```
