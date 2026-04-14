# P3 — Resolve Unresolved FLACs (v2)

## Context — read before implementing

The previous P3 attempt moved 0 files. Two failure modes observed in the logs:

1. `isrc_not_found` — 236 files had ISRCs in tags but those ISRCs weren't in
   `track_identity`. These files simply weren't ingested yet. **Run P2 first.**
   After P2, re-check how many remain.

2. `matched_isrc_but_no_destination: RuntimeError: identity missing required
   fields: album, year, disc, track` — The `track_identity` row exists but is
   incomplete, so the target path can't be derived from the identity alone.
   For these cases, derive the target path from the file's own embedded tags
   instead of from `track_identity` fields.

## Do not recreate existing files. Do not run the full test suite.
## Run P2 before running this prompt.

---

## Matching and move logic

For each FLAC in `_UNRESOLVED` and `_UNRESOLVED_FROM_LIBRARY`:

### 1. Read tags from the file itself
Use mutagen to read: `title`, `artist`, `albumartist`, `album`, `date`/`year`,
`tracknumber`, `discnumber`, `isrc`.

### 2. Match to track_identity by ISRC
Query `track_identity` where `isrc = ?` (case-insensitive, stripped).
- No match → `unmatched`, leave in place.
- Multiple matches → `ambiguous`, leave in place.
- One match → confirmed.

### 3. Derive target path
**Primary:** try to derive from `track_identity` fields (album, year, disc, track, title, artist).
**Fallback:** if any required field is missing in `track_identity`, derive entirely
from the file's own embedded tags using the same template:
`MASTER_LIBRARY/{artist}/({year}) {album}/{disc}-{track:02d}. {title} - {artist}.flac`

Use file tags for any field that is missing or empty in `track_identity`.
Log `dest_from_file_tags` in the notes column.

If both `track_identity` and file tags are missing a required field, log as
`unmatched` with note `missing_required_fields`.

### 4. Safety checks before move
- Target path must not already exist on disk.
- `asset_file` must have no row for the target path.
- If either check fails, log as `duplicate_on_disk` or `conflict`.

### 5. After move
- Insert or update `asset_file` (zone=`MASTER_LIBRARY`, path=target).
- Link to `track_identity` via `asset_link`.
- Write `provenance_event` with `ingestion_method='resolve_unresolved'`.

### 6. Fuzzy fallback (no ISRC in tags)
Only if ISRC is absent: fuzzy match on `title_norm` + `artist_norm` using
`rapidfuzz`, threshold >= 0.92. Log as `fuzzy_match_pending_review`, do NOT
move automatically.

---

## Report

Write to `/Volumes/MUSIC/logs/resolve_unresolved_v2_YYYYMMDD_HHMMSS.tsv`:
```
source_path  result  match_method  target_path  identity_id  isrc  notes
```

`result` values: `moved`, `unmatched`, `ambiguous`, `duplicate_on_disk`,
`conflict`, `fuzzy_match_pending_review`, `error`

---

## Script entrypoint

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/resolve_unresolved_v2.py [--dry-run]
```

Default: live run. `--dry-run` prints actions without writing to DB or moving files.

## Acceptance

- `--dry-run` runs cleanly and prints a summary.
- Live run moves at least the files whose ISRCs are in `track_identity`
  and whose file tags supply all required path fields.
- TSV report written.
- Print summary:
```
Total files: N
Moved: N  |  Fuzzy pending review: N  |  Unmatched: N  |  Skipped: N  |  Errors: N
Output: /Volumes/MUSIC/logs/resolve_unresolved_v2_YYYYMMDD_HHMMSS.tsv
```

## Commit

```
fix(tools): rewrite resolve_unresolved_v2 with file-tag fallback for path derivation
```
