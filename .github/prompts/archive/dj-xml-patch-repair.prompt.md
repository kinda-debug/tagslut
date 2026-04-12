# Prompt: DJ XML Patch Repair

## Context

Repo: `kinda-debug/tagslut`  
Branch: `dev`  
Canonical doc: `docs/DJ_PIPELINE.md` §Stage 4, `docs/DJ_WORKFLOW.md` §Stage 4

`tagslut dj xml patch` is the incremental re-export path. It must:

- verify the prior XML file's manifest hash (from `dj_export_state`) before
  proceeding — fail loudly if tampered or absent.
- reuse all existing `rekordbox_track_id` values from `dj_track_id_map`.
- write a new `dj_export_state` row with the updated manifest hash.
- respect the same `dj validate` gate as `dj xml emit` (pass only if a
  passing `dj_validation_state` row exists for the current `state_hash`).

## Problem Statement

The command fails or produces a broken XML. Suspected failure modes:

1. **Prior XML hash verification missing or wrong** — `dj_export_state` stores
   the XML SHA-256 hash but `xml_patch.py` may read the wrong column or not
   verify at all, allowing a tampered XML to be patched silently.
2. **TrackID reuse broken** — if `dj_track_id_map` is not joined on
   `dj_admission_id` correctly, new TrackIDs are assigned instead of reusing
   existing ones, breaking Rekordbox cue point persistence.
3. **Validate gate not enforced** — `dj xml patch` may not check
   `dj_validation_state` before proceeding (the gate is documented for emit
   but must also apply to patch).
4. **`dj_export_state` INSERT** — writing the new manifest row may conflict
   with a UNIQUE constraint if patching the same DB state twice.

## Files To Read First

- `tagslut/exec/dj_xml_patch.py` (primary)
- `tagslut/exec/dj_xml_emit.py` — reference for the validate gate and
  `dj_export_state` write pattern
- `tagslut/storage/migrations/0010_add_dj_pipeline_tables.sql` — confirm
  `dj_export_state` DDL and UNIQUE constraints
- `tagslut/storage/v3/dj_state.py` (created by `dj-validate-and-emit-repair`
  prompt — import `compute_dj_state_hash` from here)

## Required Changes

1. **Validate gate**: at the top of the patch flow, call
   `compute_dj_state_hash(conn)` and look up a passing row in
   `dj_validation_state`. If none exists, exit non-zero with:
   ```
   ERROR: no passing dj validate record for current state. Run `tagslut dj validate` first.
   ```
2. **Prior XML hash check**: read the most recent `dj_export_state` row for
   the current DB. Hash the `--in` XML file with SHA-256 and compare. If they
   differ, exit non-zero with:
   ```
   ERROR: prior XML hash mismatch — file may have been modified outside tagslut.
   ```
3. **TrackID reuse**: the XML generation loop must JOIN `dj_admission` with
   `dj_track_id_map` ON `dj_track_id_map.dj_admission_id = dj_admission.id`
   and use `dj_track_id_map.rekordbox_track_id` for every admitted track. If
   a row is missing from `dj_track_id_map` (should not happen after backfill),
   fail loudly rather than assigning a new ID silently.
4. **`dj_export_state` INSERT**: use `INSERT OR REPLACE` (keyed on the export
   session identifier) so re-patching the same state does not raise a conflict.

## Verification

```bash
# clean patch run after a prior emit
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --in rekordbox.xml \
  --out rekordbox_v2.xml

# hash mismatch must fail
echo 'tampered' >> rekordbox.xml
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --in rekordbox.xml \
  --out rekordbox_v3.xml
# ^^^ must exit non-zero with hash mismatch message

# stale validation must fail
sqlite3 "$TAGSLUT_DB" \
  "UPDATE dj_validation_state SET passed=0 WHERE id=(SELECT MAX(id) FROM dj_validation_state);"
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --in rekordbox.xml \
  --out rekordbox_v4.xml
# ^^^ must exit non-zero with validate gate message
```

## Constraints

- Import `compute_dj_state_hash` from `tagslut/storage/v3/dj_state.py`.
  Do NOT inline the hash computation.
- Do NOT alter migration files.
- TrackID values already in `dj_track_id_map` must never be changed.
- Run `poetry run mypy tagslut/exec/dj_xml_patch.py --ignore-missing-imports`.
- Run `poetry run pytest tests/ -k xml_patch --tb=short -q`.

## Commit Message

```
fix(dj): xml patch validate gate, prior-hash check, TrackID reuse from map
```
