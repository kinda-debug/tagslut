<!-- Status: Active document. Synced 2026-03-22 after DJ pipeline hardening. Historical or superseded material belongs in docs/archive/. -->

# DJ Pipeline

This is the canonical operator reference for the DJ workflow.

`tools/get --dj` and `tools/get-intake --dj` are legacy wrapper paths. They are
not the supported curated-library workflow.

Primary workflow: `tagslut intake` -> `tagslut mp3 build` or `tagslut mp3 reconcile`
-> `tagslut dj backfill` -> `tagslut dj validate` -> `tagslut dj xml emit` or
`tagslut dj xml patch`.

## Canonical 4-Stage Workflow

### Stage 1 — Intake Masters

Use the current CLI intake surface to ingest or refresh canonical masters.

```bash
poetry run tagslut intake <provider-url>
```

Outputs:
- canonical `track_identity` state
- linked master `asset_file` rows
- provenance for the intake run

Legacy compatibility note:
- `tools/get --enrich <provider-url>` still exists as a wrapper around intake behavior
- `tools/get --dj` is not a substitute for this pipeline

### Stage 2 — Build Or Reconcile MP3 Library

Canonical MP3 asset root policy:
- `MP3_LIBRARY` is the single canonical active MP3 asset root.
- `DJ_LIBRARY` is an alias to `MP3_LIBRARY` for compatibility, not a second root.
- Source/staging folders (for example `mdl/Apple`, `mdl/Apple Music`, `_work`) are provenance-only inputs and must not be treated as active reconcile roots.

Build MP3s from canonical masters when the DJ MP3 layer does not exist yet:

```bash
poetry run tagslut mp3 build \
  --db "$TAGSLUT_DB" \
  --dj-root "$DJ_LIBRARY" \
  --execute
```

Register an existing MP3 root without re-transcoding:

```bash
poetry run tagslut mp3 reconcile \
  --db "$TAGSLUT_DB" \
  --mp3-root "$MP3_LIBRARY" \
  --execute
```

Notes:
- Default is `--dry-run` (no DB writes); pass `--execute` to register rows.
- If `--mp3-root` is omitted, `tagslut mp3 reconcile` resolves in order: `$DJ_LIBRARY`, then `$MP3_LIBRARY`.

Outputs:
- `mp3_asset` rows linked to canonical identities and master assets
- `mp3_asset` provenance fields for source/copy tracking (`source_root`, `source_path`, `ingest_session`, `ingest_at`) when available

### Stage 2 Source Import Workflow (provenance-only sources preserved)

Use this flow to import from preserved source folders without promoting them to active roots:

```bash
# 1) Copy from preserved source to canonical MP3 root (skip existing files)
rsync -av --ignore-existing \
  /Volumes/MUSIC/mdl/Apple/ \
  /Volumes/MUSIC/MP3_LIBRARY/

# 2) Reconcile canonical MP3 root only
poetry run tagslut mp3 reconcile --db "$TAGSLUT_DB" --mp3-root "$MP3_LIBRARY" --execute

# 3) Admit and validate from canonical root state
poetry run tagslut dj backfill --db "$TAGSLUT_DB"
poetry run tagslut dj validate --db "$TAGSLUT_DB"
```

The source folder remains untouched and continues to serve as provenance/reference input only.

Stage 2 transcode safety:

- `mp3 build` and DJ-pool transcodes do not trust ffmpeg exit status alone.
- After each transcode, the output MP3 is validated for existence, minimum size, mutagen readability, and duration greater than 1 second.
- Validation failures raise `TranscodeError` before the output is accepted or registered.

### Stage 3 — Admit And Validate DJ Library

Bulk-admit verified MP3 assets into the curated DJ layer. This is the primary Stage 3 path:

```bash
poetry run tagslut dj backfill --db "$TAGSLUT_DB"
```

For targeted one-off repairs, admit a specific identity / MP3 asset pair:

```bash
poetry run tagslut dj admit \
  --db "$TAGSLUT_DB" \
  --identity-id <identity_id> \
  --mp3-asset-id <mp3_asset_id>
```

Validate before export:

```bash
poetry run tagslut dj validate --db "$TAGSLUT_DB"
```

Outputs:
- `dj_admission` rows
- stable `dj_track_id_map` TrackID assignments (one row per admission; immutable)
- a `dj_validation_state` audit row keyed by the current DJ DB `state_hash`
- validated DJ-library state ready for XML export only while that `state_hash` remains current

### Stage 4 — Emit Or Patch Rekordbox XML

Initial deterministic export:

```bash
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out rekordbox.xml
```

Pre-emit gate:

- `dj xml emit` now requires a prior passing `dj validate` run for the current DJ DB state.
- If `dj_admission` rows change after validation (add/remove), rerun `poetry run tagslut dj validate --db "$TAGSLUT_DB"` before emitting again.
- `--skip-validation` remains available as an emergency escape hatch, but prints the following warning to stderr:
  `WARNING: --skip-validation bypasses the dj validate gate.`
  `Use only for emergencies.`

Subsequent export preserving TrackIDs and Rekordbox cue points:

```bash
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_v2.xml
```

Outputs:
- deterministic Rekordbox XML
- stable `dj_track_id_map` assignments (reused; no reassignments)
- `dj_export_state` manifest rows with XML hash plus DB-scope metadata
- loud failure if no matching passing `dj validate` record exists for the current `state_hash`

## Operator Rule

For a curated DJ library, run the stages in order:

`intake` -> `mp3 build` or `mp3 reconcile` -> `dj backfill` -> `dj validate` -> `dj xml emit` or `dj xml patch`

For detailed discussion and legacy-wrapper context, see `docs/DJ_WORKFLOW.md`.
