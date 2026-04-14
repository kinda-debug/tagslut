# P3 — Resolve Unresolved FLACs (v2)

## Context — read before implementing

The previous version of `tools/resolve_unresolved.py` moved 0 files.
Two failure modes from the logs:

1. `isrc_not_found` (236 files) — ISRC in file tags but not in `track_identity`
   because staging was never ingested. Run P2 first, then re-run this.

2. `matched_isrc_but_no_destination: RuntimeError: identity missing required
   fields: album, year, disc, track` — `track_identity` row exists but is
   incomplete. Fix: derive the target path from the file's own embedded tags
   when `track_identity` fields are insufficient.

## Update `tools/resolve_unresolved.py` in-place. Do NOT create a new file.
## Do not recreate existing files. Do not run the full test suite.
## Run P2 first.

---

## Matching and move logic

For each FLAC in `_UNRESOLVED` and `_UNRESOLVED_FROM_LIBRARY`:

### 1. Read tags from the file
Use mutagen: `title`, `artist`, `albumartist`, `album`, `date`/`year`,
`tracknumber`, `discnumber`, `isrc`.

### 2. Match to track_identity by ISRC
Query `track_identity` where `isrc = ?` (case-insensitive, stripped).
- No match → `unmatched`, leave in place.
- Multiple matches → `ambiguous`, leave in place.
- One match → confirmed.

### 3. Derive target path
Template: `MASTER_LIBRARY/{artist}/({year}) {album}/{disc}-{track:02d}. {title} - {artist}.flac`

**Primary:** use `track_identity` fields.
**Fallback:** if any required field is missing in `track_identity`, use the
file's own embedded tags for that field. Log `dest_from_file_tags` in notes.
If both sources are missing a required field → `unmatched` with note
`missing_required_fields`.

### 4. Safety checks
- Target path must not exist on disk → else `duplicate_on_disk`.
- `asset_file` must have no row for target path → else `conflict`.

### 5. After move
- Insert or update `asset_file` (zone=`MASTER_LIBRARY`).
- Link via `asset_link` to `track_identity`.
- Write `provenance_event` with `ingestion_method='resolve_unresolved'`.

### 6. Fuzzy fallback (no ISRC)
If no ISRC in tags: fuzzy match on `title_norm` + `artist_norm` via
`rapidfuzz`, threshold >= 0.92. Result = `fuzzy_match_pending_review`,
do NOT move automatically.

---

## Report

Write to `/Volumes/MUSIC/logs/resolve_unresolved_YYYYMMDD_HHMMSS.tsv`:
```
source_path  result  match_method  target_path  identity_id  isrc  notes
```

`result` values: `moved`, `unmatched`, `ambiguous`, `duplicate_on_disk`,
`conflict`, `fuzzy_match_pending_review`, `error`

---

## Script entrypoint

Update `tools/resolve_unresolved.py` in-place. Do NOT create a new file.

```
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"
poetry run python3 tools/resolve_unresolved.py [--dry-run]
```

Default: live run. `--dry-run` prints without writing to DB or moving files.

## Acceptance

- `--dry-run` runs cleanly.
- Live run moves files whose ISRCs match `track_identity` and whose tags
  supply all required path fields.
- TSV report written.
- Print summary:
```
Total files: N
Moved: N  |  Fuzzy pending review: N  |  Unmatched: N  |  Skipped: N  |  Errors: N
```

## Commit

```
fix(tools): add file-tag fallback for path derivation in resolve_unresolved
```
