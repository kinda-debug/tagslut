# Phase 5 Post-Cutover Notes

Date: 2026-03-03  
Release: `v3.0.0 @ ac377f0`  
Rehearsal environment:
- Clone DB: `~/tmp/tagslut_clone/music_clone.db`
- Clone library subset: `~/tmp/tagslut_clone/lib` (500 FLAC files copied from `/Volumes/MUSIC/LIBRARY`)
- USB rehearsal root: `~/tmp/tagslut_clone/usb`

## 1. Classification Promotion on Clone

- Command (dry-run): `poetry run tagslut index promote-classification --db "$CLONE_DB" --dry-run`
- Command (real): `poetry run tagslut index promote-classification --db "$CLONE_DB"`
- Result: promotion succeeded via rename-column path.
- Post-run checks:
  - `classification_v1` present.
  - `classification` now reflects v2 values.
  - Distribution remained stable: `bar=8732`, `club=8691`, `remove=6037`.

## 2. Zone + ISRC Migration Behavior

- Full `run_pending()` on this legacy-style clone failed at older migration `0002` (`duplicate column name: is_dj_material`), so migration runner replay is not idempotent on this already-upgraded DB snapshot.
- Applied migration intent directly on clone:
  - `0005_zone_model_v2.up()` applied.
  - Rehearsal normalization converted zones to runbook labels: `LIBRARY`, `DJPOOL`, `ARCHIVE`.
  - Final zone counts: `LIBRARY=23344`, `ARCHIVE=110`, `DJPOOL=6`.
- ISRC index path:
  - Clone DB initially lacked `files.isrc`; added and backfilled from `canonical_isrc`.
  - First unique-index attempt failed due duplicate ISRC values.
  - Cleaned duplicate ISRC rows on clone by nulling secondary duplicates, then applied `0006_isrc_unique_index`.
  - Verified: `idx_files_isrc` exists with partial unique definition.

## 3. Intake Resolve Manifest Behavior

- Input file: `artifacts/v3.0.0/rehearsal_tracks.jsonl` (3 intents: one known-skip, one known-upgrade, one synthetic-new).
- Command:
  - `poetry run tagslut intake resolve --db "$CLONE_DB" --input artifacts/v3.0.0/rehearsal_tracks.jsonl --output artifacts/v3.0.0/rehearsal_manifest.json`
- Result summary: `Manifest: 1 new, 1 upgrades, 1 skipped`.
- Output manifest written: `artifacts/v3.0.0/rehearsal_manifest.json`.

## 4. Gig Build + DJ Review App Behavior

- Gig build commands:
  - Dry-run and real run both completed for `Rehearsal Set` using `dj_flag:true`.
  - Real run exported tracks under USB rehearsal root and produced a manifest.
- Rekordbox/PIONEER behavior:
  - `pyrekordbox` in this environment exposes `Rekordbox6Database` (not legacy `Rb6Database`) and cannot create a new DB file.
  - Added compatibility fallback in `tagslut.exec.usb_export` to write `PIONEER/rekordbox.db` as a lightweight export DB when native create/open is unavailable.
  - Verified file exists: `~/tmp/tagslut_clone/usb/PIONEER/rekordbox.db`.
  - Verified fallback table contains 40 exported tracks.
- DJ review app:
  - Launched with clone DB at `127.0.0.1:5999`.
  - HTTP probe returned `200`, index page rendered expected markers.

## Surprises / TODOs

- `run_pending()` should not be used blindly against heavily evolved legacy DB snapshots without a migration state baseline; add a guarded rehearsal runner for clone DBs.
- One rehearsal track had no persisted MP3 in `dj_pool` despite successful export counts; investigate pool synchronization and stale `dj_pool_path` references.
- Implement a full native Rekordbox6 create path when pyrekordbox adds stable support; fallback DB is functional for audit but not a full Rekordbox library DB.
