# DO NOT recreate existing files. DO NOT modify tagslut source code or DB.
# This prompt operates on the filesystem only — no DB writes.

# Absorb RBX_USB mdl/bpdl FLACs back to main staging

## Context

Beatport FLAC downloads were moved to `/Volumes/RBX_USB 1/mdl/bpdl/` for
space reasons. They need to be moved back to `/Volumes/MUSIC/mdl/bpdl/` so
the normal intake pipeline can process them.

## Source

`/Volumes/RBX_USB 1/mdl/bpdl/` — all `.flac` files, flat or nested.

## Destination

`/Volumes/MUSIC/mdl/bpdl/` — create if not exists.

## Rules

- Collision handling: if a file with the same name already exists at the
  destination, do NOT overwrite. Move the source file to
  `/Volumes/MUSIC/mdl/bpdl/_conflicts/` instead and log it.
- Preserve directory structure relative to `/Volumes/RBX_USB 1/mdl/bpdl/`.
- Move, do not copy. Verify file exists at destination before removing source.
- Skip non-FLAC files silently.
- Skip the single FLAC at
  `/Volumes/RBX_USB 1/DJ_LIBRARY/_UNRESOLVED/` — out of scope.

## Output

- Dry-run by default: print each planned move (src → dst) without executing.
- Pass `--apply` to execute moves.
- Print summary: N moved, N conflicts, N skipped.
- Log moves to `/Volumes/MUSIC/mdl/bpdl/_absorb_log_YYYYMMDD.txt`.

## Implementation

- Script: `tools/absorb_rbx_bpdl.py`
- Python stdlib only: `os`, `pathlib`, `shutil`, `argparse`, `datetime`.
- Do not import tagslut modules.

## Commit

```
feat(tools): add script to absorb RBX_USB bpdl FLACs back to mdl staging
```
