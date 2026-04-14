# P3 — Resolve Unresolved FLACs

## Purpose
For every file in `MASTER_LIBRARY/_UNRESOLVED` and
`MASTER_LIBRARY/_UNRESOLVED_FROM_LIBRARY`: attempt to match to a
`track_identity` row by ISRC. Matched files are moved to their correct
MASTER_LIBRARY path and linked in the DB. Unmatched files stay put and
are logged.

## Prerequisites
P1 and P2 must have run. Use the most recent inventory TSV and intake sweep
TSV from `/Volumes/MUSIC/logs/`.

## Do not recreate existing files. Do not run the full test suite.

---

## Matching logic

For each FLAC in the two `_UNRESOLVED` directories:

1. Read ISRC from embedded tags (`isrc` Vorbis tag, uppercase).
2. If ISRC found: query `track_identity` where `isrc = ?`.
   - If exactly one match: this is a confirmed match.
   - If multiple matches: log as ambiguous, skip move.
   - If no match: log as unmatched, skip move.
3. If no ISRC in tags: attempt fuzzy title+artist match against
   `track_identity` (`artist_norm`, `title_norm`). Only accept if
   similarity >= 0.92 (use `rapidfuzz`). Log match method.
4. Never move a file based on fuzzy match alone without logging it
   separately as `fuzzy_match` in the report so it can be reviewed.

## Move logic (confirmed ISRC matches only, by default)

Target path: derive from `track_identity` fields using the same folder
template as MASTER_LIBRARY: `{artist}/({year}) {album}/{disc}-{track}. {title} - {artist}.flac`

Before moving:
- Check that target path does not already exist. If it does, log as
  `duplicate_on_disk` and skip.
- Check that `asset_file` has no row for the target path. If it does,
  log and skip.

After moving:
- Insert or update `asset_file` with the new path, zone=`MASTER_LIBRARY`.
- Link to `track_identity` via `asset_link`.
- Write a `provenance_event` row with `ingestion_method='resolve_unresolved'`.

## Report

Write to `/Volumes/MUSIC/logs/resolve_unresolved_YYYYMMDD_HHMMSS.tsv`:
```
source_path  result  match_method  target_path  identity_id  isrc  notes
```

`result` values: `moved`, `unmatched`, `ambiguous`, `duplicate_on_disk`,
`fuzzy_match_pending_review`, `error`

## Script entrypoint

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/resolve_unresolved.py
```

Add `--dry-run` flag that prints what would happen without moving or writing
to DB. Default is dry-run=False.

## Acceptance

Script runs to completion. TSV report written. Print summary:
```
Total files: N
Moved: N  |  Fuzzy pending review: N  |  Unmatched: N  |  Skipped: N  |  Errors: N
Output: /Volumes/MUSIC/logs/resolve_unresolved_YYYYMMDD_HHMMSS.tsv
```

## Commit

```
feat(tools): add resolve_unresolved.py to match and promote _UNRESOLVED FLACs
```
