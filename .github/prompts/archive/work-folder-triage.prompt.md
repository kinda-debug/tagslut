# work-folder-triage — Triage and clean up `/Volumes/MUSIC/_work`

## Hard rules

- Do not recreate existing files.
- Do not modify `tagslut/` source code.
- Do not write to the DB (read-only queries only).
- Do not rely on folder names alone — every delete/move must be justified by verification (DB / MASTER_LIBRARY checks below).

## Context

`/Volumes/MUSIC/_work` contains pipeline leftovers from before the FRESH DB era.
The FRESH DB is at `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`.
The task is to safely delete what is confirmed redundant and move what is valuable
to `staging/` for intake.

Repo changes are limited to adding a standalone tool script + tests.
Operational actions (when `--execute`) are filesystem moves/deletes only.

---

## Scope

- Add `tools/triage_work_folder.py` (stdlib only).
- Add `tests/tools/test_triage_work_folder.py` (pytest).
- Do not touch any other paths.

---

## Step 1 — Inventory and classification (dry-run by default)

Write a standalone Python script `tools/triage_work_folder.py` (stdlib only).

For each audio file (`.flac`, `.mp3`, `.m4a`) found recursively under `--work-root`,
classify it as exactly one of:

1. `in_db_path` — exact path match in SQLite `asset_file.path`
2. `in_db_isrc` — ISRC extracted from filename via:
   `re.search(r"\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]", filename)`
   then matched against SQLite `track_identity.isrc`
3. `in_master_library` — normalized basename match against a recursive scan of
   `--master-library` (case-insensitive, with leading track-number prefixes stripped)
4. `unknown` — none of the above

Output a TSV report to stdout and to
`/Volumes/MUSIC/_work/_triage_report_YYYYMMDD.tsv` with columns:
  `subdir | filename | size_mb | status | matched_path`

where `status` is one of: `in_db_path`, `in_db_isrc`, `in_master_library`,
`unknown`.

CLI:
```
python tools/triage_work_folder.py \
  --work-root /Volumes/MUSIC/_work \
  --master-library /Volumes/MUSIC/MASTER_LIBRARY \
  --db /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db
```

---

## Step 2 — Execute triage actions (`--execute`)

After the report is generated, apply the following rules with a second pass
`--execute` flag on the same script:

### A) Delete-eligible subdirs (only delete verified-redundant audio)

These subdirs are expected to be safe-to-clear, but deletion is still gated per-file:
only delete files whose `status` is one of `in_db_path`, `in_db_isrc`, `in_master_library`.
If any `unknown` exists in a delete-eligible subtree, do not delete it; instead log an error.

- `_work/quarantine/` — 50 GB filesystem snapshot
- `_work/fix/rejected_because_existing_24bit/` — 12 FLACs, all in DB
- `_work/cleanup_20260308_220000/` — reports/exports, 0 audio
- `_work/absolute_dj_mp3/` — M3U8 playlists only, 0 audio
- `_work/gig_runs/` — artwork/metadata only, 0 audio
- `_work/fix/_DISCARDED_20260225_171845/` — 16 FLACs (special rule below)

**Special rule: `_DISCARDED_20260225_171845/`**
- Check each of its 16 FLACs against MASTER_LIBRARY by normalized basename.
- If ALL 16 are `in_master_library`, delete the directory.
- If ANY are not, move the non-matching files to `/Volumes/MUSIC/staging/tidal/` and leave a clear log entry.

### B) Rescue subdirs (move files to staging based on verification + rule)

Moves are allowed even if a file is verified present elsewhere, but the intent is:
- Move `unknown` files to staging.
- Skip (do nothing) for files verified present in DB/MASTER_LIBRARY unless a specific rule says otherwise.

- `_work/fix/_quarantine/` — 122 FLACs, no ISRCs in filenames, pre-pipeline era.
  Move all to `/Volumes/MUSIC/staging/pre_pipeline/` for future intake.

- `_work/fix/tagslut_clone/lib/Volumes/MUSIC/LIBRARY/` — 221 FLACs from
  ROON_RECOVER and _UNRESOLVED. Move all to
  `/Volumes/MUSIC/staging/pre_pipeline/` (flatten into subfolders by source:
  `roon_recover/`, `unresolved/`).

- `_work/bpdl_jimi_jules_20260220/` — 1 FLAC
  (`18. Animal Trainer, Jimi Jules - Wide feat. Jimi Jules (Original Mix).flac`),
  not in DB. Move to `/Volumes/MUSIC/staging/bpdl/`.

- `_work/fix/conflict_same_dest/` — 6 hash-prefixed FLACs not in DB.
  Move to `/Volumes/MUSIC/staging/pre_pipeline/conflicts/`.

- `_work/fix/path_too_long/` — 3 hash-prefixed FLACs not in DB.
  Move to `/Volumes/MUSIC/staging/pre_pipeline/conflicts/`.

- `_work/fix/missing_tags/` — 141 FLACs. 137 in DB (skip). 4 unknown:
  - `1-02. Prins Thomas - KLHouse.flac` → move to `staging/tidal/`
  - The 3 Glitterbox Radio double-`.flac.flac` files → delete (radio excerpts,
    malformed)

### After all moves and deletions, delete the now-empty `_work/fix/` tree and
`_work/` itself if empty.

---

## Step 3 — Log

Write a summary log to `/Volumes/MUSIC/_work/_triage_executed_YYYYMMDD.txt`:
  - Files deleted: N (list paths)
  - Files moved to staging: N (list src → dst)
  - Subdirs removed: list
  - Errors: list

---

## Implementation notes

- Dry-run by default. `--execute` to apply.
- Basename matching against MASTER_LIBRARY:
  - Normalize basename by stripping leading track-number prefixes like `^\d+[\.\s\-]+` and case-folding.
  - Build a set of normalized basenames by walking MASTER_LIBRARY once (it’s large; still do it once).
- Do not use `shutil.rmtree` on non-empty dirs unless all contents have been
  accounted for by the report first.
- `staging/pre_pipeline/` may not exist — create with `mkdir -p`.
- Script is idempotent: re-running dry-run after `--execute` should show
  0 actions remaining.

---

## Tests

`tests/tools/test_triage_work_folder.py`:

1. File in DB by path → status `in_db_path`, not moved
2. File with ISRC in filename matching DB → status `in_db_isrc`, not moved
3. File with basename matching MASTER_LIBRARY → status `in_master_library`,
   deleted in execute mode for delete-eligible subdirs
4. Unknown file in rescue subdir → moved to correct staging destination
5. Double `.flac.flac` Glitterbox file → deleted
6. Dry-run: no filesystem changes regardless of status

Use tmp_path fixtures. Mock DB with sqlite3 in-memory.

Run: `poetry run pytest tests/tools/test_triage_work_folder.py -v`

---

## Commit

`feat(tools): add work-folder triage script and execute cleanup`
