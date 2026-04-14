# Library Cleanup — Runbook (updated)

## Current state (as of 2026-04-14)

P1 (inventory) ran successfully.
P2 (intake) ran but ingested 0 tracks — fixed in v2.
P3 (resolve unresolved) ran but moved 0 files — fixed in v2.
P4 (mp3 consolidation) ran but moved 0 files — blocked on P2/P3.
P5 (final audit + rekordbox) ran; 800 files still unaccounted for.

Root cause: P2 never actually called the CLI correctly, so staging FLACs
were never ingested into the DB, so P3 and P4 had nothing to match against.

## Correct run order going forward

```
P2v2  →  P3v2  →  P4 (re-run)  →  P5 (re-run)
```

P1 does not need to re-run unless you want a fresh baseline.

## Run commands

```bash
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"

# Step 1 — ingest staging batches into DB
poetry run python3 tools/intake_sweep_v2.py

# Step 2 — resolve _UNRESOLVED FLACs (dry-run first)
poetry run python3 tools/resolve_unresolved_v2.py --dry-run
poetry run python3 tools/resolve_unresolved_v2.py

# Step 3 — consolidate MP3s
poetry run python3 tools/mp3_consolidation.py --dry-run
poetry run python3 tools/mp3_consolidation.py

# Step 4 — final audit + rekordbox XML
poetry run python3 tools/final_audit.py
poetry run python3 tools/rekordbox_export.py
```

## What each step does

| Script | Does | Output |
|--------|------|--------|
| intake_sweep_v2.py | Calls `tagslut intake spotiflac` for every batch in staging (with and without .txt) | `logs/intake_sweep_v2_*.tsv` |
| resolve_unresolved_v2.py | Matches _UNRESOLVED FLACs by ISRC, falls back to file tags for path derivation | `logs/resolve_unresolved_v2_*.tsv` |
| mp3_consolidation.py | Moves MP3s from `_spotiflac_next` and `mp3_leftorvers` to MP3_LIBRARY | `logs/mp3_consolidation_*.tsv` |
| final_audit.py | Re-scans all locations, reports remaining unaccounted files | `logs/final_audit_*.tsv` |
| rekordbox_export.py | Generates Rekordbox XML from mp3_asset table | `rekordbox_fresh_*.xml` |

## Files that will remain after all steps (expected)

- Files with no ISRC in tags and no fuzzy match → manual review
- `fuzzy_match_pending_review` entries in resolve log → manual review
- `no_master_flac` MP3s in consolidation log → no FLAC counterpart exists
- `_work/fix` and `_work/quarantine` → never touched, your call

## DB and paths

- DB: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`
- All logs: `/Volumes/MUSIC/logs/`
- Staging: `/Volumes/MUSIC/staging/`
- Master: `/Volumes/MUSIC/MASTER_LIBRARY/`
- MP3: `/Volumes/MUSIC/MP3_LIBRARY/`
