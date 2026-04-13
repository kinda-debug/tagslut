# consolidate-mp3-leftovers

## Goal
Move all audio files from `/Volumes/MUSIC/mp3_leftorvers` into
`/Volumes/MUSIC/MP3_LIBRARY_CLEAN`, update DB asset_file paths, and
remove the now-empty source tree.

## Do not recreate existing files
This prompt implements new filesystem work only. Do not touch any
existing CLI commands, migrations, or exec helpers.

## Context
- DB: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`
- Source: `/Volumes/MUSIC/mp3_leftorvers` (1,554 artist dirs, unmanaged legacy MP3s)
- Destination: `/Volumes/MUSIC/MP3_LIBRARY`
- `mp3_consolidate` exec helper already exists at
  `tagslut/exec/mp3_consolidate.py` — use it if it supports
  arbitrary source/dest, otherwise implement inline logic here.

## Steps

### 1. Dry run first
Invoke `mp3_consolidate` (or equivalent logic) with `--dry-run` against
`/Volumes/MUSIC/mp3_leftorvers` → `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`.
Print a summary: total files, conflicts (dest path already exists),
format breakdown (mp3/m4a/other).

### 2. Conflict handling
- If dest file already exists AND source and dest are byte-identical:
  skip source, do not overwrite.
- If dest file already exists AND files differ: move source to
  `/Volumes/MUSIC/_work/cleanup_mp3_consolidate_conflicts/` with full
  relative path preserved. Do not overwrite dest.
- If dest does not exist: move file (do not copy — use os.rename or
  shutil.move).

### 3. DB path update
For every file successfully moved, update `asset_file.file_path` in the
DB where the old path matches. Use a single transaction per batch of
1,000 rows. Log updated row count.

### 4. Remove empty dirs
After all moves, walk `/Volumes/MUSIC/mp3_leftorvers` and remove any
empty directories bottom-up. If the root dir is empty after cleanup,
remove it too.

### 5. Report
Print final summary:
- Files moved
- Files skipped (already at dest, identical)
- Files in conflict dir
- DB rows updated
- Dirs removed

## Constraints
- Never delete audio files — only move them
- Never overwrite a dest file that differs from source
- If any volume is not mounted, abort with clear error
- Run targeted pytest for any existing mp3_consolidate tests before
  and after
- Commit with: `chore(filesystem): consolidate mp3_leftorvers into MP3_LIBRARY_CLEAN`
