# DO NOT recreate existing files. DO NOT modify tagslut source code or DB.
# This prompt operates exclusively on the filesystem under /Volumes/MUSIC/playlists/.

# Playlist Consolidation

## Objective

Parse, deduplicate, classify, and consolidate all playlist files under
`/Volumes/MUSIC/playlists/` into a clean canonical flat structure.
Archive superseded files. Do not delete anything permanently.

## Scope

**In scope:**
- `/Volumes/MUSIC/playlists/` and all subdirectories

**Explicitly out of scope — do not touch:**
- `/Volumes/MUSIC/tagslut/config/dj/crates/`
- `/Volumes/MUSIC/MASTER_LIBRARY/playlists/`
- `/Volumes/MUSIC/_work/`
- `/Volumes/MUSIC/staging/`


## Input

Enumerate all `.m3u` and `.m3u8` files recursively under
`/Volumes/MUSIC/playlists/`. For each file collect:
- Absolute path
- File mtime (via `os.path.getmtime`)
- Track list: all non-comment, non-empty lines stripped of leading/trailing
  whitespace. Normalize paths to basename only for deduplication comparison
  (path prefixes differ across copies).

## Deduplication logic

Two playlist files are **content-duplicates** if their normalized track lists
are identical (same basenames, same order). When duplicates are found, keep
the copy with the **latest mtime**. If mtimes are equal, prefer the copy
whose path is shallowest (fewest path components).

## Classification

Classify each file into one of four buckets based on path and filename
patterns:

| Bucket | Criteria |
|---|---|
| `CANONICAL` | Lives directly in `/Volumes/MUSIC/playlists/` (not a subdir), not a content-duplicate of a newer file, not matching JUNK patterns |
| `ARCHIVE` | Lives in a subdirectory (`playlists/playlists/`, `pees/`, `pees/p/`, `PLAYLISTS_FIXED/`, `Playlists_phase_v3/`, `_m3u_backup_*/`), OR is a content-duplicate of a newer canonical file, OR filename contains a timestamp pattern `_\d{8}_\d{6}` or `-\d{8}-\d{6}` |
| `JUNK` | Single-track named file (filename matches artist-title pattern with no DJ/PARTY prefix), OR filename is ` .m3u8` (space only), OR filename ends in `.bak` |
| `SKIP` | `.txt`, `.DS_Store`, `.zip`, `.xml`, non-playlist files |


## Output — what to produce

### 1. Dry-run report (always)

Print a report to stdout grouped by bucket. For each file show:
- path
- mtime (ISO format)
- track count
- if ARCHIVE: reason (duplicate_of=<path>, or subdirectory, or timestamp)
- if JUNK: reason

### 2. Consolidation (only when `--apply` flag passed)

**CANONICAL files:** leave in place. No moves.

**ARCHIVE files:** move to `/Volumes/MUSIC/playlists/_archive_YYYYMMDD/`
where YYYYMMDD is today's date. Preserve relative subpath within the archive
dir (e.g. `pees/foo.m3u` → `_archive_YYYYMMDD/pees/foo.m3u`).

**JUNK files:** move to `/Volumes/MUSIC/playlists/_junk_YYYYMMDD/`.

**SKIP files:** leave in place.

After moving, print a summary: N canonical kept, N archived, N junked.

## Implementation notes

- Use Python stdlib only: `os`, `pathlib`, `shutil`, `datetime`, `argparse`.
- Do not import tagslut modules.
- Script location: `tools/consolidate_playlists.py`
- Entry point: `python tools/consolidate_playlists.py [--apply]`
- Idempotent: running twice without `--apply` is safe. Running with `--apply`
  twice is a no-op (files already moved).
- Read playlist files with `errors='replace'` to handle encoding issues.
- Skip symlinks.
- Log all moves to `_consolidation_log_YYYYMMDD.txt` in the playlists root.

## Commit

```
feat(tools): add playlist consolidation script
```
