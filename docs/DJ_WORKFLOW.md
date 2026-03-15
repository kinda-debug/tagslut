<!-- Status: Active document. Synced 2026-03-14 after DJ pipeline explicit-stages refactor + Lexicon metadata backfill. Historical or superseded material belongs in docs/archive/. -->

# DJ Workflow

DJ pool contract: see `docs/DJ_POOL.md` for the downstream-only boundary and defaults.

## Deprecation Notice

`tools/get --dj` is deprecated. Use the 4-stage DJ pipeline instead.

For a curated DJ library, the only supported workflow is:
`tagslut mp3 reconcile` or `tagslut mp3 build` -> `tagslut dj admit` or
`tagslut dj backfill` -> `tagslut dj validate` -> `tagslut dj xml emit` or
`tagslut dj xml patch`.

Why this exists: `tools/get --dj` still follows legacy wrapper logic with two
divergent runtime paths. For diagnosis and evidence, see
`docs/audit/DJ_WORKFLOW_AUDIT.md`.

## Overview

The 4-stage DJ pipeline is the only supported workflow for building a curated,
repeatable DJ library. Each stage writes explicit DB-backed state and is safe
to re-run. Use this document as the canonical operator reference without
needing to read any other DJ doc first.

## Explicit 4-Stage Pipeline (Canonical)

The canonical DJ workflow is a linear, auditable pipeline. Each stage is safe to re-run
and has explicit DB state as output. Run stages in order:

### Stage 1 — MP3 Registration (`mp3 reconcile` or `mp3 build`)

If you already have DJ MP3s on disk and want to register them against canonical
identities without re-transcoding:

```bash
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" \
  --mp3-root "$DJ_LIBRARY" \
  --execute
```

Matches each MP3 to a `track_identity` row via ISRC (preferred) or title+artist.
Registers the file in `mp3_asset`. Use `--dry-run` (default) to preview matches.

If you need to generate DJ MP3s from canonical FLAC masters instead of reconciling
an existing MP3 library, use `mp3 build`:

```bash
poetry run tagslut mp3 build \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-root "$DJ_LIBRARY" \
  --execute
```

Use `mp3 reconcile` when MP3 files already exist. Use `mp3 build` when the DJ MP3
layer still needs to be created from canonical masters.

### Stage 2 — DJ Admission (`dj backfill` or `dj admit`)

Promote all registered `mp3_asset` rows (`status=verified`) into the curated DJ admission table:

```bash
poetry run tagslut dj backfill \
  --db "$TAGSLUT_DB"
```

Or admit a single track by identity + asset IDs:

```bash
poetry run tagslut dj admit \
  --db "$TAGSLUT_DB" \
  --identity-id <id> \
  --mp3-asset-id <id>
```

Writes rows to `dj_admission`. Idempotent: already-admitted tracks are skipped.

### Stage 3 — DJ Validation (`dj validate`)

Before export, validate that admitted tracks still have the expected files and metadata:

```bash
poetry run tagslut dj validate \
  --db "$TAGSLUT_DB"
```

Use this stage after admission and before XML export. Validation is the contract check
that keeps Stage 4 deterministic.

### Stage 4 — Rekordbox Export (`dj xml emit` and `dj xml patch`)

Use `dj xml emit` for a fresh deterministic export:

Write a deterministic Rekordbox-compatible XML from all admitted `dj_admission` rows:

```bash
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --output rekordbox.xml
```

- Assigns stable TrackIDs (persisted in `dj_track_id_map` so cue points survive re-imports)
- Records a SHA-256 manifest hash in `dj_export_state`
- Raises if validation finds missing MP3 files or empty metadata (use `--skip-validation` to override)

Use `dj xml patch` when the DJ library has changed and you need a fresh XML
without resetting Rekordbox cue points:

```bash
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --output rekordbox_v2.xml
```

- Verifies the prior XML file's manifest hash before proceeding (fails loudly if tampered)
- All existing `rekordbox_track_id` values are preserved from `dj_track_id_map`
- Adds a new row to `dj_export_state` with the updated manifest hash

---

## Why The 4-Stage Model

The explicit pipeline exists because `tools/get --dj` does not provide a stable
or auditable contract for curated DJ library builds. The audit diagnosis is:

- the wrapper has two hidden runtime paths depending on whether promote or precheck wins
- there is no durable MP3 registration layer unless you use `mp3_asset`
- validation and export state become implicit side effects instead of explicit tables

For the full diagnosis, read `docs/audit/DJ_WORKFLOW_AUDIT.md`. For day-to-day
operator use, stay on the 4-stage pipeline above.

## Lexicon Metadata Backfill

Backfills `energy`, `danceability`, `happiness`, `popularity`, `bpm`, and `key` from a
Lexicon DJ SQLite export into `track_identity.canonical_payload_json`. Also logs beat-grid
(tempomarker) coverage to `reconcile_log`. Safe to run repeatedly — overwrites only
`lexicon_*` prefixed keys, never canonical fields.

```bash
# Dry run — preview match counts, no DB writes
python -m tagslut.dj.reconcile.lexicon_backfill --dry-run

# Live run (defaults to EPOCH_2026-03-04/music_v3.db + /Volumes/MUSIC/lexicondj.db)
python -m tagslut.dj.reconcile.lexicon_backfill

# Custom paths
python -m tagslut.dj.reconcile.lexicon_backfill \
  --db  /path/to/music_v3.db \
  --lex /Volumes/MUSIC/lexicondj_update.db
```

Match strategy (in priority order):
1. `beatport_id` — if Lexicon has `streamingService='beatport'`
2. `spotify_id`  — if Lexicon has `streamingService='spotify'`
3. Normalized `artist + title` text match

All match decisions are appended to `reconcile_log` with `source='lexicondj'`,
`run_id`, `confidence` (`high` / `medium` / `low`), and `details_json`.

Verify after run:
```bash
sqlite3 "$TAGSLUT_DB" "
SELECT action, confidence, COUNT(*) n
FROM reconcile_log
WHERE source='lexicondj'
GROUP BY 1,2 ORDER BY 3 DESC;
"
```

---

## Legacy Downloader Shortcut

`tools/get --dj` is a legacy shell wrapper that runs precheck, download, tagging/enrichment,
promote, and DJ MP3 export in a single flow. It has two divergent code paths depending on
whether tracks were newly promoted or already existed in inventory (precheck-hit).

**Deprecated:** this path is not supported for building a final curated DJ library.
See `docs/DJ_WORKFLOW.md` for the canonical 4-stage pipeline. Use `tools/get --dj`
only for legacy ad-hoc intake where non-deterministic wrapper behavior is acceptable.

To build DJ copies for already-promoted masters outside of a download flow, run:

```bash
poetry run tagslut dj backfill --db "$TAGSLUT_DB"
```

## DJ Library Root

Set your DJ library root once and re-use it across workflows:

```bash
set -a
source .env
set +a

export MASTER_LIBRARY="${MASTER_LIBRARY:-${LIBRARY_ROOT:-$VOLUME_LIBRARY}}"
export PLAYLIST_ROOT="${PLAYLIST_ROOT:-$MASTER_LIBRARY/playlists}"
export DJ_LIBRARY="${DJ_LIBRARY:-${DJ_MP3_ROOT:?set DJ_LIBRARY in .env}}"
export DJ_PLAYLIST_ROOT="${DJ_PLAYLIST_ROOT:-$DJ_LIBRARY}"
```

`MASTER_LIBRARY` is the FLAC source of truth. `PLAYLIST_ROOT` holds Roon-readable library playlists. `DJ_LIBRARY` is the derived DJ library, and `DJ_PLAYLIST_ROOT` holds DJ playlists with absolute paths for Rekordbox/Lexicon workflows. Legacy scripts can still read `LIBRARY_ROOT`, `DJ_MP3_ROOT`, or `DJ_LIBRARY_ROOT` via aliases from `.env`.

## Pipeline Choice

Canonical curated-library pipeline:
- Follow the 4-stage workflow in this document for `mp3` → `dj admission` → `dj validate` → `dj xml`.

Preferred v3 pool-builder pipeline for cohort exports:
- Follow `docs/OPERATIONS.md` for `dj-candidates` → `dj-profile` → `dj-ready` → `dj-pool-plan/run`.
- For operator use, prefer `poetry run tagslut dj pool-wizard` for plan/execute.
- Use `scripts/dj/build_pool_v3.py` or the `make dj-pool-*` targets only when you explicitly need the lower-level builder.

Legacy v2 pipeline (XLSX/overrides-based):
- Uses `tagslut dj curate/export` with `config/dj/track_overrides.csv`.
- Keep this path only if you are explicitly operating from XLSX inputs.

## DJ Pool Wizard

`tagslut dj pool-wizard` is the primary operator workflow for building a final MP3 DJ pool from `MASTER_LIBRARY`.

### Usage

Plan-first, non-interactive:

```bash
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root /tmp/dj_pool_runs \
  --non-interactive \
  --profile "$VOLUME_WORK/gig_runs/gig_2026_03_13/profile.json"
```

Interactive TTY wizard:

```bash
poetry run tagslut dj pool-wizard \
  --db "$TAGSLUT_DB" \
  --master-root "$MASTER_LIBRARY" \
  --dj-cache-root "$DJ_LIBRARY" \
  --out-root /tmp/dj_pool_runs
```

What it does:

- locks the cohort to flagged tracks under `MASTER_LIBRARY`
- writes cohort health, duplicate analysis, selected rows, plan rows, and manifest artifacts into a timestamped run directory
- uses relinked or cached MP3 sources when available, and only transcodes on execute when no reusable MP3 source exists
- keeps `--plan` mutation-free; file copies and DB writes only happen under `--execute`

Use `scripts/dj/build_pool_v3.py` only as the lower-level script path when you need the script-level builder directly. Operator docs should point to `tagslut dj pool-wizard`.

## Staged-Root DJ Phase

For an already-staged FLAC root, `process-root` now has a DJ phase:

```bash
python -m tagslut intake process-root \
  --db "$V3_DB" \
  --root "$STAGING_ROOT" \
  --phases dj \
  --dry-run
```

What it does:

- looks up the active identity for each staged FLAC
- writes BPM and key from v3 canonical identity data when available
- falls back to Essentia for BPM/key/energy when canonical values are missing
- transcodes staged FLACs to the configured DJ pool when not in dry-run mode

Notes:
- `--dry-run` currently previews the DJ phase only
- if Essentia is not installed, fallback analysis is skipped with a warning
- the deterministic v3 builder path is still the preferred export route for a curated DJ pool

## Legacy v2 Quick Export (Safe Mode)

Once tracks have been classified, just run:

```bash
tagslut dj export --safe --output-root $DJ_USB_ROOT
```

Nothing else needed. No prompts.

To export a specific crate:

```bash
tagslut dj export --safe --crate peak-time --output-root $DJ_USB_ROOT
```

## Legacy v2 Commands

### tagslut dj curate

Preview which tracks pass DJ curation filters (dry run).

Example:

```bash
poetry run tagslut dj curate --input-xlsx $DJ_XLSX \
  --policy config/dj/dj_curation_usb_v8.yaml \
  --output-root $DJ_USB_ROOT_YES
```

### tagslut dj export

Curate and transcode DJ library to USB output root.

Example:

```bash
poetry run tagslut dj export --input-xlsx $DJ_XLSX \
  --policy config/dj/dj_curation_usb_v8.yaml \
  --output-root $DJ_USB_ROOT_YES \
  --jobs 4 --detect-keys
```

## DJ Curation Policy Schema

Recommended: `config/dj/dj_curation_usb_v8.yaml`

Other policies live in `config/dj/` (v6/v7/relaxed), but v8 is the current tuned default.

```yaml
name: dj_curation_usb_v8
version: 2026-02-25.dj_curation_usb_v8
description: Techno boost + rock nuke (per-genre boost/demote).
lane: dj
rules:
  duration_min: 180
  duration_max: 720
  bpm_min: 110
  bpm_max: 150
  bpm_optimal_min: 118
  bpm_optimal_max: 135
  score_safe_min: 4
  score_block_max: -2
  artist_blocklist_path: config/blocklists/non_dj_artists.txt
  artist_reviewlist_path: config/blocklists/borderline_artists.txt
  genre_filters:
    - experimental
    - jazz
    - blues
    - acoustic
    - folk
  dj_genres:
    - techno
    - tech house
    - melodic house & techno
    - deep tech
    - electronic
    - electronica
    - minimal
    - house
    - deep house
  anti_dj_genres:
    - rock
    - world
    - nu disco / disco
    - dance / pop
    - indie
    - alternative
  genre_boost_mult:
    techno: 2
  genre_demote_mult:
    rock: -20
```

## Blocklist Files

- `config/blocklists/non_dj_artists.txt` (hard reject)
- `config/blocklists/borderline_artists.txt` (manual review)

Format: one artist per line, `#` for comments.

## KeyFinder Integration

- Uses `keyfinder-cli` if available on PATH.
- If not installed, key detection is skipped gracefully.
- Enables `--detect-keys` flag for `tagslut dj export`.

## Future

Playlist import as classification source:

`tagslut dj import --source spotify --playlist "DJ Set 2024-08"`

`tagslut dj import --source roon --playlist "Friday Night"`

Every track → verdict=safe, crate=<playlist name>

Requires: Spotify/Tidal API auth, Roon local API

## Review App (Manual Control)

If you want a UI for artist/album/track decisions (OK / Not OK), use the review app:

```bash
tagslut dj review-app --db "$TAGSLUT_DB"
```

See `docs/DJ_REVIEW_APP.md` for auto‑verdict, filters, and USB export.
