<!-- Status: Active document. Synced 2026-03-22 after DJ pipeline hardening. Historical or superseded material belongs in docs/archive/. -->

# DJ Pipeline

This is the canonical operator reference for the DJ workflow.

`tools/get --dj` and `tools/get-intake --dj` are legacy wrapper paths. They are
not the supported curated-library workflow.

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
  --mp3-root "$DJ_LIBRARY" \
  --execute
```

Outputs:
- `mp3_asset` rows linked to canonical identities and master assets

### Stage 3 — Admit And Validate DJ Library

Bulk-admit verified MP3 assets into the curated DJ layer:

```bash
poetry run tagslut dj backfill --db "$TAGSLUT_DB"
```

Or admit a specific identity / MP3 asset pair:

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
- validated DJ-library state ready for XML export

### Stage 4 — Emit Or Patch Rekordbox XML

Initial deterministic export:

```bash
poetry run tagslut dj xml emit \
  --db "$TAGSLUT_DB" \
  --out rekordbox.xml
```

Subsequent export preserving TrackIDs and Rekordbox cue points:

```bash
poetry run tagslut dj xml patch \
  --db "$TAGSLUT_DB" \
  --out rekordbox_v2.xml
```

Outputs:
- deterministic Rekordbox XML
- stable `dj_track_id_map` assignments
- `dj_export_state` manifest rows with XML hash plus DB-scope metadata

## Operator Rule

For a curated DJ library, run the stages in order:

`intake` -> `mp3 build` or `mp3 reconcile` -> `dj admit` or `dj backfill` -> `dj validate` -> `dj xml emit` or `dj xml patch`

For detailed discussion and legacy-wrapper context, see `docs/DJ_WORKFLOW.md`.
