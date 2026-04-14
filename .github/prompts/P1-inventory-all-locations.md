# P1 — Inventory All Locations

## Purpose
Produce a read-only TSV report of every audio file across all unresolved
locations. No files are moved, renamed, or written to any library directory.
This report is the input for all subsequent prompts (P2–P5).

## Do not recreate existing files. Do not run the full test suite.

---

## Output

Write to `/Volumes/MUSIC/logs/inventory_YYYYMMDD_HHMMSS.tsv`
(create `/Volumes/MUSIC/logs/` if it does not exist).

Columns (tab-separated, one header row):
```
location  path  ext  size_bytes  isrc  upc  artist  title  in_asset_file  in_track_identity  asset_zone  identity_isrc_match
```

- `location`: one of: staging_spotiflacnext, staging_spotiflac, staging_other,
  master_unresolved, master_unresolved_from_library, mp3_library_spotiflac_next,
  mp3_leftovers, work_fix
- `path`: absolute path
- `ext`: file extension lowercase (.flac, .m4a, .mp3)
- `size_bytes`: integer
- `isrc`: from embedded tags (Vorbis `isrc`, M4A `----:com.apple.iTunes:ISRC`,
  MP3 `TSRC`). Empty string if absent.
- `upc`: from embedded tags. Empty string if absent.
- `artist`: from embedded tags. Empty string if absent.
- `title`: from embedded tags. Empty string if absent.
- `in_asset_file`: 1 if path exists in `asset_file.path`, else 0
- `in_track_identity`: 1 if isrc is non-empty and matches any `track_identity.isrc`, else 0
- `asset_zone`: value of `asset_file.zone` if matched, else empty
- `identity_isrc_match`: the matched ISRC from `track_identity` if found, else empty

## Locations to scan

```python
LOCATIONS = {
    "staging_spotiflacnext": "/Volumes/MUSIC/staging/SpotiFLACnext",
    "staging_spotiflac":     "/Volumes/MUSIC/staging/SpotiFLAC",
    "staging_other":         "/Volumes/MUSIC/staging",  # top-level files only, not subfolders already covered
    "master_unresolved":     "/Volumes/MUSIC/MASTER_LIBRARY/_UNRESOLVED",
    "master_unresolved_from_library": "/Volumes/MUSIC/MASTER_LIBRARY/_UNRESOLVED_FROM_LIBRARY",
    "mp3_library_spotiflac_next": "/Volumes/MUSIC/MP3_LIBRARY/_spotiflac_next",
    "mp3_leftovers":         "/Volumes/MUSIC/mp3_leftorvers",
    "work_fix":              "/Volumes/MUSIC/_work/fix",
}
EXTENSIONS = {".flac", ".m4a", ".mp3"}
DB_PATH = "/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db"
```

For `staging_other`, skip subdirectories named `SpotiFLACnext` and `SpotiFLAC`
to avoid double-counting.

## Implementation

Write as `tools/inventory_all.py`. Use:
- `mutagen` for tag reading (soft-fail per file, empty strings on error)
- `sqlite3` for DB lookups — load all `asset_file.path` values into a set,
  load all `track_identity.isrc` values into a set, at startup (not per-file)
- Progress: print a dot every 500 files to stderr
- Errors: log per-file errors to stderr, continue

## Script entrypoint

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/inventory_all.py
```

## Acceptance

Script runs to completion without crashing. TSV file exists with a header row
and at least one data row. Print final summary to stdout:
```
Total files scanned: N
In DB: N  |  Not in DB: N
Has ISRC: N  |  No ISRC: N
Matched to track_identity: N
Output: /Volumes/MUSIC/logs/inventory_YYYYMMDD_HHMMSS.tsv
```

## Commit

```
feat(tools): add inventory_all.py for full location audit
```
