# P4 — MP3 Library Consolidation

## Purpose
Integrate `MP3_LIBRARY/_spotiflac_next` and `mp3_leftorvers` into the main
`MP3_LIBRARY` tree. For each MP3, find its corresponding MASTER_LIBRARY FLAC
by ISRC. If found, move the MP3 to sit alongside its FLAC counterpart
(same artist/album folder, `.mp3` extension). If not found, log and leave.

## Prerequisites
P1, P2, and P3 must have run. Use inventory TSV for context.

## Do not recreate existing files. Do not run the full test suite.

---

## Folder convention for MP3_LIBRARY

MP3_LIBRARY mirrors MASTER_LIBRARY structure exactly:
`MP3_LIBRARY/{artist}/({year}) {album}/{disc}-{track}. {title} - {artist}.mp3`

This is the single naming convention. No other layout is used.

## Matching logic

For each MP3 in `_spotiflac_next` and `mp3_leftorvers`:

1. Read ISRC from tags (ID3 `TSRC` frame, or `----:com.apple.iTunes:ISRC`
   for M4A-derived MP3s).
2. Query `asset_file` joined with `asset_link` joined with `track_identity`
   where `track_identity.isrc = ?` and `asset_file.zone = 'MASTER_LIBRARY'`.
3. If exactly one FLAC found: derive target MP3 path from the FLAC path by
   replacing the MASTER_LIBRARY prefix with MP3_LIBRARY and extension with
   `.mp3`.
4. If no FLAC found: log as `no_master_flac`, leave file in place.
5. If multiple FLACs found: log as `ambiguous`, leave file in place.

## Move logic

Before moving:
- Check target path does not already exist. If it does and sizes match
  within 1%: log as `duplicate`, delete source (do not keep two copies).
  If sizes differ significantly: log as `conflict`, skip.
- Create target directory if needed.

After moving:
- Insert or update `mp3_asset` row with new path, zone=`MP3_LIBRARY`,
  link to `track_identity` via `identity_id`.

## Report

Write to `/Volumes/MUSIC/logs/mp3_consolidation_YYYYMMDD_HHMMSS.tsv`:
```
source_path  result  target_path  isrc  identity_id  notes
```

`result` values: `moved`, `no_master_flac`, `ambiguous`, `duplicate`,
`conflict`, `error`

## Script entrypoint

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/mp3_consolidation.py
```

Add `--dry-run` flag. Default is dry-run=False.

## Acceptance

Script runs to completion. TSV written. Print summary:
```
Total MP3s: N
Moved: N  |  No master FLAC: N  |  Duplicate removed: N  |  Conflicts: N  |  Errors: N
Output: /Volumes/MUSIC/logs/mp3_consolidation_YYYYMMDD_HHMMSS.tsv
```

## Commit

```
feat(tools): add mp3_consolidation.py to integrate MP3 leftovers into MP3_LIBRARY
```
