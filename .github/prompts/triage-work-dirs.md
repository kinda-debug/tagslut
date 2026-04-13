# triage-work-dirs

## Goal
Safe, DB-verified cleanup of `_work/fix` and `_work/quarantine` on
`/Volumes/MUSIC`. For every audio file in these dirs, cross-check
against MASTER_LIBRARY in the DB before taking any action. Never delete
a file that is not confirmed present in MASTER_LIBRARY.

## Do not recreate existing files
This prompt does filesystem work only. No code changes to the CLI.

## DB
`/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`

## Targets

### Step 1 — Remove exact duplicate quarantine tree (safe, no DB needed)
`_work/quarantine/MUSIC/_quarantine/tracks/` and
`_work/quarantine/MUSIC/_quarantine/quarantine/` are byte-for-byte
identical directory trees (same files, same paths, duplicated).

Action: count files in both, confirm counts match, then delete
`_work/quarantine/MUSIC/_quarantine/tracks/` only. Keep `quarantine/`.

### Step 2 — Remove `_work/fix/tagslut_clone` (safe, no DB needed)
This is a git repo clone, not audio. Confirm with `git -C` check,
then delete unconditionally.

### Step 3 — DB cross-check and conditional delete for all remaining audio

For each of these directories, scan all `.flac`, `.mp3`, `.m4a` files:

- `/Volumes/MUSIC/_work/quarantine/MUSIC/_quarantine/quarantine/`
- `/Volumes/MUSIC/_work/fix/_quarantine/`
- `/Volumes/MUSIC/_work/fix/_DISCARDED_20260225_171845/`
- `/Volumes/MUSIC/_work/fix/rejected_because_existing_24bit/`
- `/Volumes/MUSIC/_work/fix/conflict_same_dest/`
- `/Volumes/MUSIC/_work/fix/missing_tags/`
- `/Volumes/MUSIC/_work/fix/path_too_long/`

For each file:
1. Look up the file's ISRC (from FLAC tag or DB `asset_file.isrc`)
2. If ISRC found: query DB for any `asset_file` row with same ISRC
   whose `file_path` starts with `/Volumes/MUSIC/MASTER_LIBRARY`.
   If confirmed present → mark as SAFE_TO_DELETE.
3. If no ISRC: query DB by filename similarity (artist + title from
   tags). If confirmed present in MASTER_LIBRARY → mark SAFE_TO_DELETE.
4. If no match found in DB → mark as KEEP (do not touch).

After scanning, print a report:
- Total files scanned per directory
- SAFE_TO_DELETE count and total size
- KEEP count and total size
- Sample of KEEP files (first 10)

**Do not delete anything yet.** Write the delete list to:
`/Users/georgeskhawam/Projects/tagslut/artifacts/triage_work_delete_candidates.txt`

And the keep list to:
`/Users/georgeskhawam/Projects/tagslut/artifacts/triage_work_keep.txt`

### Step 4 — Execute deletions
After writing the lists, ask for confirmation by printing:

```
READY TO DELETE: N files (X GB)
Run with --execute to proceed.
```

If `--execute` flag is passed to the script, proceed with deletion of
all SAFE_TO_DELETE files, then remove empty directories.

## Output
Commit after --execute run:
`chore(filesystem): triage _work dirs — delete N files verified in MASTER_LIBRARY`

## Constraints
- Never delete a KEEP file
- Never delete files from MASTER_LIBRARY itself
- If MUSIC volume not mounted, abort
- Run as a standalone Python script saved to `tools/triage_work_dirs.py`
- No changes to any existing CLI or migration files
