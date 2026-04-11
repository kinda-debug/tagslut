# DO NOT recreate existing files. DO NOT modify DB or audio files directly.
# DO NOT modify any existing intake, register, or index commands.

# Ingest staging/mp3_to_sort_intake and clean up source folders

## Context

The absorb-mp3-to-sort script ran on 2026-04-12 and produced:
- 38 unique MP3s moved to `/Volumes/MUSIC/staging/mp3_to_sort_intake/`
- 11 duplicates quarantined to `/Volumes/MUSIC/mp3_to_sort/_dupes_20260412/`
- Original source `/Volumes/MUSIC/mp3_to_sort/` now empty of audio files

A second copy of the pre-absorb source exists at
`/Users/georgeskhawam/Music/mp3_to_sort/` (49 files) — this is the original
location before the absorb ran on the volume copy. It is now redundant.

## Task A — Register mp3_to_sort_intake into the DB

Use the existing `tagslut index register-mp3` command (from register-mp3-only
prompt) once it is implemented. If that command is not yet available, implement
this task as a standalone script `tools/ingest_mp3_to_sort_intake.py` using the
same logic: scan `staging/mp3_to_sort_intake/`, INSERT OR IGNORE into `files`
with:
  - zone                 = "staging"
  - download_source      = "mp3_to_sort"
  - ingestion_method     = "manual_sort"
  - ingestion_confidence = "uncertain"

Dry-run by default. `--execute` to commit.

Print: scanned, skipped (already in DB), inserted, failed.

## Task B — Clean up source folders

After Task A completes with `--execute` and reports 0 failures:

1. Delete `/Users/georgeskhawam/Music/mp3_to_sort/` and all contents.
   This is the home-directory copy — redundant now that intake has run.

2. Delete `/Volumes/MUSIC/mp3_to_sort/_dupes_20260412/` — operator has
   confirmed these duplicates are disposable.

3. If `/Volumes/MUSIC/mp3_to_sort/` is now empty (audio files only, ignoring
   .DS_Store), delete it too.

Do NOT delete `/Volumes/MUSIC/staging/mp3_to_sort_intake/` — files must remain
on disk after DB registration (they are the canonical copies).

## Implementation order

1. Check if `tagslut index register-mp3` exists (`tagslut index --help`).
   - If yes: use it with `--root /Volumes/MUSIC/staging/mp3_to_sort_intake
     --source mp3_to_sort --zone staging`.
   - If no: implement `tools/ingest_mp3_to_sort_intake.py` as described above.
2. Run dry-run, confirm output looks correct.
3. Run with `--execute`.
4. Perform Task B cleanup only after DB insert reports success.

## Tests (if new script created)

`tests/tools/test_ingest_mp3_to_sort_intake.py`:
- MP3 not in DB → inserted with correct zone/source/method
- MP3 already in DB → skipped (INSERT OR IGNORE)
- dry-run → zero inserts

Run: `poetry run pytest tests/tools/test_ingest_mp3_to_sort_intake.py -v`

## Commit

`feat(tools): ingest mp3_to_sort_intake into DB and clean up source folders`
