# CLEANUP MANIFEST (2026-04-12)

## Deleted

- (none) — all Phase 1 “confirmed junk” targets were not present in this repo snapshot.

## Archived

- docs/archive/ROADMAP.md → docs/ROADMAP.md — restored roadmap to canonical location; added §7.4 pointing to this manifest.
- docs/archive/DJ_POOL.md → docs/DJ_POOL.md — restored DJ pool doc to canonical location.

- scripts/auto_env.py → scripts/archive/auto_env.py — unreferenced one-off `.env` materializer (not referenced by CI, package, or tests).
- scripts/backfill_v3_provenance_from_logs.py → scripts/archive/backfill_v3_provenance_from_logs.py — unreferenced one-off provenance backfill helper.
- scripts/capture_post_release_snapshot.py → scripts/archive/capture_post_release_snapshot.py — unreferenced post-release snapshot helper (writes under `artifacts/`).
- scripts/reconcile_track_overrides.py → scripts/archive/reconcile_track_overrides.py — unreferenced one-off maintenance script for `config/dj/track_overrides.csv`.

- tools/dj_review_app.py → tools/archive/dj_review_app.py — unreferenced launcher shim.
- tools/dj_usb_sync.py → tools/archive/dj_usb_sync.py — unreferenced legacy DJ USB sync / Rekordbox XML helper.
- tools/fix_blocklist.py → tools/archive/fix_blocklist.py — unreferenced one-off blocklist pruning helper.
- tools/claude-clean → tools/archive/claude-clean — unreferenced convenience wrapper (calls `tools/review/claude_clean.py`).
- tools/get-all → tools/archive/get-all — unreferenced legacy end-to-end pipeline orchestrator.
- tools/get-auto → tools/archive/get-auto — unreferenced legacy precheck+download helper.
- tools/get-sync → tools/archive/get-sync — deprecated compatibility alias; unreferenced.

## Left in place (uncertain)

- tools/dj_usb_analyzer.py — compatibility shim name collides with existing `tools/archive/dj_usb_analyzer.py`; left in place to avoid ambiguity.
- artifacts/**/*.log — log files remain under `artifacts/` (including `artifacts/intake/logs/` and `artifacts/logs/`). Policy requires moving them to `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/`, but this pass did not move them.

## Not touched (active)

- No changes under `tagslut/`, `tests/`, `config/`, `supabase/`, `.github/workflows/`, `pyproject.toml`, `poetry.lock`.
- No changes to `tools/get`, `tools/get-intake`, or anything under `tools/review/`.
