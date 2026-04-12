# DO NOT recreate existing files. DO NOT modify tagslut/ source code.
# DO NOT write to the DB. DO NOT rely on folder/file names to infer intent.
# Every delete or move must be justified by per-file verification.

# Generalized loose-audio triage tool

## Purpose

Replace the work-folder-specific `tools/triage_work_folder.py` (which has not
yet been implemented) with a general-purpose tool that can be run against ANY
directory tree on the volume. The same verification logic applies everywhere:
classify each audio file against the FRESH DB and MASTER_LIBRARY, then act
according to a per-root rules config.

Do NOT implement `tools/triage_work_folder.py`. Implement
`tools/triage_loose_audio.py` instead.

---

## Scope

- New file: `tools/triage_loose_audio.py` (stdlib only, no tagslut imports)
- New file: `tools/triage_rules.json` (default rules config, checked into repo)
- New file: `tests/tools/test_triage_loose_audio.py`
- Do not touch any other files.

---

## Classification

For each audio file (`.flac`, `.mp3`, `.m4a`, `.aiff`, `.wav`) found recursively
under a scan root, assign exactly one status in priority order:

1. `in_db_path` — exact path string in `asset_file.path`
2. `in_db_isrc` — ISRC from filename `\[([A-Z]{2}[A-Z0-9]{3}\d{7})\]`
   matched against `track_identity.isrc`
3. `in_master_library` — normalized basename found in MASTER_LIBRARY scan
   (case-fold, strip leading `^\d+[\.\s\-]+` prefix)
4. `unknown` — none of the above

MASTER_LIBRARY basename index is built once at startup (walk the tree, store
normalized basenames in a set). It is large — use `os.walk`, do not use
subprocess or find.

---

## CLI

```
python tools/triage_loose_audio.py \
  --scan-root /Volumes/MUSIC/_work \
  --rules tools/triage_rules.json \
  --db /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db \
  --master-library /Volumes/MUSIC/MASTER_LIBRARY \
  [--execute]
```

Dry-run by default. `--execute` to apply moves and deletes.

---

## Rules config format (`tools/triage_rules.json`)

A JSON array of rule objects. Rules are matched in order; first match wins.
Each rule has:

```json
{
  "match_prefix": "/Volumes/MUSIC/_work/quarantine",
  "action": "delete",
  "only_if_status": ["in_db_path", "in_db_isrc", "in_master_library"],
  "rescue_dest": null,
  "note": "50 GB filesystem snapshot"
}
```

Fields:
- `match_prefix` (string): file path must start with this prefix
- `action` (string): `"delete"` | `"rescue"` | `"skip"`
- `only_if_status` (array or null): for `delete` — only delete if file status
  is in this list; if null, delete regardless of status. For `rescue` — ignored
  (always move unknown; skip files already in DB/library). 
- `rescue_dest` (string or null): destination directory for `rescue` action.
  Required when action is `rescue`.
- `note` (string): human-readable description, not used by code.

**Fallback rule**: if no rule matches, action is `skip`.

---

## Default `tools/triage_rules.json`

Include the following rules covering all known loose paths on this machine:

```json
[
  {
    "match_prefix": "/Volumes/MUSIC/_work/quarantine",
    "action": "delete",
    "only_if_status": ["in_db_path", "in_db_isrc", "in_master_library"],
    "rescue_dest": null,
    "note": "Filesystem snapshot — all content is copies"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/fix/rejected_because_existing_24bit",
    "action": "delete",
    "only_if_status": ["in_db_path", "in_db_isrc", "in_master_library"],
    "rescue_dest": null,
    "note": "Superseded by 24-bit copies in library"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/cleanup_20260308_220000",
    "action": "delete",
    "only_if_status": null,
    "rescue_dest": null,
    "note": "Dated snapshot of reports/exports — no audio"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/absolute_dj_mp3",
    "action": "delete",
    "only_if_status": null,
    "rescue_dest": null,
    "note": "M3U8 playlists only"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/gig_runs",
    "action": "delete",
    "only_if_status": null,
    "rescue_dest": null,
    "note": "Gig metadata/artwork only"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/fix/_DISCARDED_20260225_171845",
    "action": "delete",
    "only_if_status": ["in_db_path", "in_db_isrc", "in_master_library"],
    "rescue_dest": "/Volumes/MUSIC/staging/tidal",
    "note": "Rescue unknowns to staging/tidal; delete confirmed redundant"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/fix/_quarantine",
    "action": "rescue",
    "only_if_status": null,
    "rescue_dest": "/Volumes/MUSIC/staging/pre_pipeline",
    "note": "Pre-pipeline FLACs, no ISRCs"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/fix/tagslut_clone",
    "action": "rescue",
    "only_if_status": null,
    "rescue_dest": "/Volumes/MUSIC/staging/pre_pipeline",
    "note": "ROON_RECOVER and _UNRESOLVED FLACs"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/bpdl_jimi_jules_20260220",
    "action": "rescue",
    "only_if_status": null,
    "rescue_dest": "/Volumes/MUSIC/staging/bpdl",
    "note": "Single Beatport FLAC not in DB"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/fix/conflict_same_dest",
    "action": "rescue",
    "only_if_status": null,
    "rescue_dest": "/Volumes/MUSIC/staging/pre_pipeline/conflicts",
    "note": "Pipeline rename conflicts"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/fix/path_too_long",
    "action": "rescue",
    "only_if_status": null,
    "rescue_dest": "/Volumes/MUSIC/staging/pre_pipeline/conflicts",
    "note": "Path-length rejects"
  },
  {
    "match_prefix": "/Volumes/MUSIC/_work/fix/missing_tags",
    "action": "rescue",
    "only_if_status": null,
    "rescue_dest": "/Volumes/MUSIC/staging/tidal",
    "note": "Unknown files rescued; verified files skipped"
  },
  {
    "match_prefix": "/Volumes/MUSIC/mp3_leftorvers",
    "action": "rescue",
    "only_if_status": null,
    "rescue_dest": "/Volumes/MUSIC/staging/pre_pipeline/mp3_leftovers",
    "note": "Legacy MP3 pool — rescue unknowns only"
  },
  {
    "match_prefix": "/Volumes/MUSIC/MP3_LIBRARY_CLEAN",
    "action": "skip",
    "only_if_status": null,
    "rescue_dest": null,
    "note": "Large legacy MP3 library — do not touch yet"
  },
  {
    "match_prefix": "/Volumes/MUSIC/Other ",
    "action": "rescue",
    "only_if_status": null,
    "rescue_dest": "/Volumes/MUSIC/staging/pre_pipeline/other",
    "note": "Misc loose FLACs with trailing space in dir name"
  }
]
```

---

## Special cases handled in code (not in rules)

1. **Double-extension files** (e.g. `foo.flac.flac`): always delete, regardless
   of rule. Log as `malformed_extension`.

2. **`rescue` action for verified files**: if `action == "rescue"` and status is
   `in_db_path` or `in_db_isrc`, skip (do not move — already tracked). If
   status is `in_master_library`, skip too. Only move `unknown` files.

3. **`delete` with `rescue_dest` set** (the `_DISCARDED` rule): for files
   whose status is NOT in `only_if_status`, move to `rescue_dest` instead of
   deleting. Do not leave them in place.

4. **Destination collision**: if a file already exists at the destination path,
   append `_1`, `_2` etc. to the stem before the extension.

5. **Empty directory cleanup**: after execute, remove directories that are empty
   (recursively, bottom-up) within each processed scan root.

---

## Output

TSV report to stdout and to `{scan_root}/_triage_report_YYYYMMDD.tsv`:
  `path | subdir | filename | size_mb | status | action_taken | dest_path`

Summary log to `{scan_root}/_triage_log_YYYYMMDD.txt`:
  - Deleted: N files (list)
  - Rescued: N files (list src → dst)
  - Skipped: N files
  - Malformed (deleted): N files
  - Errors: list

---

## Implementation notes

- Stdlib only: `os`, `pathlib`, `sqlite3`, `json`, `re`, `shutil`, `argparse`,
  `datetime`, `collections`.
- Build MASTER_LIBRARY basename index once: `{normalized_basename: first_match_path}`.
  Normalize = `re.sub(r"^\d+[\.\s\-]+", "", name).lower()`.
- DB connection is read-only: `sqlite3.connect(f"file:{db}?mode=ro", uri=True)`.
- `--scan-root` can be passed multiple times to triage several roots in one run.
- Script is idempotent.

---

## Tests

`tests/tools/test_triage_loose_audio.py`:

1. `in_db_path` — exact path in DB → status correct, not moved in execute
2. `in_db_isrc` — ISRC in filename matches DB → status correct
3. `in_master_library` — normalized basename matches → status correct
4. `unknown` in rescue rule → moved to rescue_dest in execute mode
5. `unknown` in delete rule with rescue_dest → moved to rescue_dest (not deleted)
6. `in_db_path` in delete rule → deleted in execute mode
7. Double `.flac.flac` → always deleted regardless of rule
8. `rescue` rule + verified file → skipped (not moved)
9. Destination collision → stem suffix appended
10. Dry-run → zero filesystem changes
11. `--scan-root` passed twice → both roots processed

Use `tmp_path`, in-memory sqlite3. Mock MASTER_LIBRARY as a tmp dir.

Run: `poetry run pytest tests/tools/test_triage_loose_audio.py -v`

---

## Commit

`feat(tools): add generalized triage_loose_audio script with rules config`
