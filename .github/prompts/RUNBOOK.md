# Library Cleanup — Runbook (updated 2026-04-14)

## Current state

P1 (inventory) — done.
P2 (intake) — `intake_sweep_v2.py` exists, run this.
P3 (resolve unresolved) — `resolve_unresolved.py` exists, updated in-place.
P4 (mp3 consolidation) — `mp3_consolidation.py` exists, re-run after P2/P3.
P5 (final audit + rekordbox) — `final_audit.py` and `rekordbox_export.py` exist.

Root cause of zero moves: P2 never ingested staging FLACs into DB,
so P3 and P4 had nothing to match against.

---

## Run order

```
P2  →  P3  →  P4  →  P5
```

## Commands

```bash
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"

# P2 — ingest all staging batches
poetry run python3 tools/intake_sweep_v2.py

# P3 — resolve _UNRESOLVED FLACs (dry-run first)
poetry run python3 tools/resolve_unresolved.py --dry-run
poetry run python3 tools/resolve_unresolved.py

# P4 — consolidate MP3s (dry-run first)
poetry run python3 tools/mp3_consolidation.py --dry-run
poetry run python3 tools/mp3_consolidation.py

# P5 — final audit + rekordbox XML
poetry run python3 tools/final_audit.py
poetry run python3 tools/rekordbox_export.py
```

## What each script does

| Script | Does | Output |
|--------|------|--------|
| intake_sweep_v2.py | Calls `tagslut intake spotiflac` for every batch (with and without .txt) | `logs/intake_sweep_v2_*.tsv` |
| resolve_unresolved.py | Matches _UNRESOLVED FLACs by ISRC, falls back to file tags for path | `logs/resolve_unresolved_*.tsv` |
| mp3_consolidation.py | Moves MP3s from `_spotiflac_next` and `mp3_leftorvers` to MP3_LIBRARY | `logs/mp3_consolidation_*.tsv` |
| final_audit.py | Re-scans all locations, reports remaining unaccounted files | `logs/final_audit_*.tsv` |
| rekordbox_export.py | Generates Rekordbox XML from mp3_asset table | `rekordbox_fresh_*.xml` |

## Files that will remain after all steps (expected)

- No ISRC + no fuzzy match → manual review
- `fuzzy_match_pending_review` in resolve log → manual review
- `no_master_flac` in consolidation log → no FLAC counterpart exists
- `_work/fix` and `_work/quarantine` → never touched

## Key paths

- DB: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`
- Logs: `/Volumes/MUSIC/logs/`
- Staging: `/Volumes/MUSIC/staging/`
- Master: `/Volumes/MUSIC/MASTER_LIBRARY/`
- MP3: `/Volumes/MUSIC/MP3_LIBRARY/`
