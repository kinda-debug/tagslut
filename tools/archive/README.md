# Tools Archive

This directory contains archived scripts that have been superseded or are no longer actively maintained.

## Contents

### delete_flac_with_mp3_match.py

One-off script to delete FLAC files that have matching MP3 versions.
- Contains hardcoded paths (`/Users/georgeskhawam/Music/yesflac`, `/Users/georgeskhawam/Music/yesmp3`)
- Not part of standard workflow
- Kept for reference only

**Archived:** 2026-02-14

### promote_by_tags_versions/

Historical snapshots of `promote_by_tags.py` from Jan-Feb 2026.
- Contains 16 timestamped versions
- The active version is `tools/review/promote_by_tags.py`

**Archived:** 2026-02-14

### match_unknowns_to_epoch_2026_02_08.py

Original version of the epoch matching script.
- Superseded by `tools/review/match_unknowns_to_epoch_2026_02_08_fast.py`
- The fast variant is optimized and preferred

**Archived:** 2026-02-14

### reassess_playlist_duration_unknowns.py

Original duration reassessment script that requires OAuth tokens.
- Superseded by `scripts/reassess_playlist_duration_unknowns_tokenless.py`
- The tokenless variant is preferred (no OAuth required)

**Archived:** 2026-02-14

## Policy

- Do not use scripts from this archive in active workflows
- Scripts here are kept for reference and potential recovery
- If you need functionality from an archived script, check for the active replacement first
