# Library Cleanup — Runbook

Run these prompts in order via Codex. Each one is self-contained.
Do not skip steps — each prompt reads output from the previous one.

## Order

```
P1  →  P2  →  P3  →  P4  →  P5
```

## Run command (for each prompt)

```bash
cd /Users/georgeskhawam/Projects/tagslut
codex exec --full-auto - < .github/prompts/P1-inventory-all-locations.md
codex exec --full-auto - < .github/prompts/P2-staging-intake-sweep.md
codex exec --full-auto - < .github/prompts/P3-resolve-unresolved.md
codex exec --full-auto - < .github/prompts/P4-mp3-library-consolidation.md
codex exec --full-auto - < .github/prompts/P5-final-audit-and-rekordbox-export.md
```

## What each prompt does

| Prompt | What it does | Output |
|--------|-------------|--------|
| P1 | Read-only scan of all unresolved locations. No writes. | `logs/inventory_*.tsv` |
| P2 | Run `tagslut intake` for all unprocessed staging batches. Writes to DB only. | `logs/intake_sweep_*.tsv` |
| P3 | Match `_UNRESOLVED` FLACs to DB by ISRC. Move confirmed matches to MASTER_LIBRARY. | `logs/resolve_unresolved_*.tsv` |
| P4 | Move MP3s from `_spotiflac_next` and `mp3_leftorvers` into main MP3_LIBRARY tree. | `logs/mp3_consolidation_*.tsv` |
| P5 | Final audit of remaining files. Generate Rekordbox XML from DB. | `logs/final_audit_*.tsv`, `rekordbox_fresh_*.xml` |

## If something goes wrong

- All scripts except P3 and P4 are read-only or additive.
- P3 and P4 support `--dry-run` — run with that flag first to preview.
- All TSV reports are in `/Volumes/MUSIC/logs/`.
- DB is at `/Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db`.
- `_work/fix` and `_work/quarantine` are never touched by any prompt.

## After P5

- Review `rekordbox_fresh_*.xml` before importing into Rekordbox.
- Import via Rekordbox: File → Import Library → select the XML.
- Any files flagged as `no_master_flac` in P4 report need manual review.
- Any files flagged as `fuzzy_match_pending_review` in P3 report need manual review.
