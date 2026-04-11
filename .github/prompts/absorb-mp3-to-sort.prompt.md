# DO NOT recreate existing files. DO NOT modify tagslut source code or DB.
# This prompt operates on the filesystem only — no DB writes.

# Absorb mp3_to_sort into MP3_LIBRARY_CLEAN (dedup check first)

## Context

`/Volumes/MUSIC/mp3_to_sort/` contains 49 flat MP3s — manually collected
tracks that never went through the pipeline. Keep any that are not already
present elsewhere. Discard (archive) duplicates.

## Source

`/Volumes/MUSIC/mp3_to_sort/` — all `.mp3` files, flat directory.

## Deduplication check

For each file, check for presence in both:
- `/Volumes/MUSIC/MP3_LIBRARY_CLEAN/` (recursive)
- `/Volumes/MUSIC/mp3_leftorvers/` (recursive)

Match by **basename only** (case-insensitive, ignoring leading track number
prefix patterns like `01 `, `1-01 `, `07 ` etc. — strip these before
comparing). A match on the normalized basename means the file is a duplicate.

## Classification

- **UNIQUE**: no match found in either location → move to
  `/Volumes/MUSIC/mdl/mp3_to_sort_intake/` for pipeline processing.
- **DUPLICATE**: match found → move to
  `/Volumes/MUSIC/mp3_to_sort/_dupes_YYYYMMDD/`.

## Output

- Dry-run by default: print each file with classification and matched path
  if duplicate.
- Pass `--apply` to execute moves.
- Print summary: N unique (moved to intake), N duplicates (archived).
- Log to `/Volumes/MUSIC/mp3_to_sort/_absorb_log_YYYYMMDD.txt`.

## Implementation

- Script: `tools/absorb_mp3_to_sort.py`
- Python stdlib only: `os`, `pathlib`, `shutil`, `argparse`, `datetime`, `re`.
- Do not import tagslut modules.
- Read filenames with `errors='replace'`.

## Commit

```
feat(tools): add script to absorb mp3_to_sort with dedup check
```
