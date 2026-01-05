## Step-0 Canonical Library Ingestion

This pipeline performs a content-first ingestion of recovered FLAC files before any
tagging or library tooling. Paths are treated as ephemeral inputs only.

### Core guarantees

* **Content is truth**: decisions are made from file integrity and audio metadata.
* **Strict integrity**: `flac --test` must pass for canonical selection.
* **One canonical copy per recording**: duplicates are resolved deterministically.
* **Explicit outcomes**: every file is classified as CANONICAL, REDUNDANT,
  REACQUIRE, or TRASH.

### CLI usage

```
python tools/ingest/run.py \
  --inputs /Volumes/recovery_source_1 /Volumes/recovery_source_2 ~/Downloads/flac \
  --canonical-root /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --quarantine-root /Volumes/RECOVERY_TARGET/Root/QUARANTINE \
  --db artifacts/db/music.db \
  --library-tag recovery-2025-01 \
  --strict-integrity \
  --progress
```

Run with `--execute` to apply the plan. Without it, the command performs a dry run
and writes `plan.json` and `reacquire_manifest.csv`.

### Canonical path format

`Artist/(YYYY) Album/01. Track Title.flac`

Disc handling uses `1-01. Track Title.flac`. Tags are normalized to Unicode NFC
and unsafe characters are replaced.

### Database additions

Step-0 adds additive tables for audio content, integrity results, identity hints,
canonical mapping, reacquire manifests, and scan events. These are designed to be
idempotent and safe to re-run.

### Example outputs

* `docs/examples/step0_plan.json`
* `docs/examples/reacquire_manifest.csv`
