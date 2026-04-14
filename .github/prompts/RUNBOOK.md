# Library Cleanup — Runbook (final)

## Current state (2026-04-14 23:37)

336 files remain unaccounted for. Breakdown:

| Location | Files | Status |
|----------|-------|--------|
| staging_spotiflacnext | 177 | 147 are MP3 derivatives (wait for P7). 30 originals need intake. |
| staging_spotiflac | 26 | 24 need direct intake run |
| master_unresolved | 48 | 44 have no ISRC — permanent manual backlog |
| master_unresolved_from_library | 85 | 55 have no ISRC — permanent manual backlog |
| mp3_library_spotiflac_next | 72 | In DB, need P4 re-run after P7 |
| mp3_leftovers | 378 | No master FLAC exists — permanent manual backlog |

Rekordbox XML is at `/Volumes/MUSIC/rekordbox_fresh_20260414_1.xml` (454 tracks).

---

## Remaining automated work

```bash
cd /Users/georgeskhawam/Projects/tagslut
export PATH="$HOME/.local/bin:$PATH"

# P7 — intake remaining batches, re-promote, re-consolidate MP3s
codex exec --full-auto - < .github/prompts/P7-final-intake-pass.md

# After P7 completes:
poetry run python3 tools/final_audit.py
poetry run python3 tools/rekordbox_export.py
```

---

## Permanent manual backlog (do not attempt to automate)

These files require human decision. Open the TSV in a spreadsheet:

```
/Volumes/MUSIC/logs/resolve_unresolved_20260414_230445.tsv
  → filter result=fuzzy_match_pending_review (67 files)
  → filter result=unmatched (25 files)

/Volumes/MUSIC/logs/final_audit_20260414_233727.tsv
  → filter location=master_unresolved (44 no ISRC)
  → filter location=master_unresolved_from_library (55 no ISRC)
  → filter location=mp3_leftovers (378 files, no master FLAC)
```

For fuzzy matches: review the `target_path` column. If correct, move manually
and update `asset_file` zone to `MASTER_LIBRARY`. If wrong, delete source or
leave in `_UNRESOLVED`.

For no-ISRC files: either tag them manually with an ISRC and re-run
`resolve_unresolved.py`, or accept them as unresolvable and delete or archive.

For mp3_leftovers with no master FLAC: these are MP3-only tracks. Either
accept them into MP3_LIBRARY directly (without a FLAC counterpart) or discard.

---

## Key paths

- DB: `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`
- Logs: `/Volumes/MUSIC/logs/`
- Rekordbox XML: `/Volumes/MUSIC/rekordbox_fresh_20260414_1.xml`
- Staging: `/Volumes/MUSIC/staging/`
- Master: `/Volumes/MUSIC/MASTER_LIBRARY/`
- MP3: `/Volumes/MUSIC/MP3_LIBRARY/`
