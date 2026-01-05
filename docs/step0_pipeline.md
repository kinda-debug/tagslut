## Consolidated Scanning Workflow

**Note**: The original Step-0 tiered-hashing pipeline has been archived to `tools/archive/ingest/`. The current production workflow uses `tools/integrity/scan.py` for all scanning operations.

See **[FAST_WORKFLOW.md](FAST_WORKFLOW.md)** for the recommended workflow:

```bash
# Fast scan (no integrity checks)
python3 tools/integrity/scan.py /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --db artifacts/db/music.db \
  --library recovery \
  --zone accepted \
  --no-check-integrity \
  --incremental \
  --progress

# Generate duplicate clusters
python3 tools/decide/recommend.py --db artifacts/db/music.db --output plan.json

# Verify winners only
python3 tools/integrity/scan.py /path/to/winners \
  --db artifacts/db/music.db \
  --check-integrity \
  --recheck \
  --progress
```

---

## Legacy Step-0 Pipeline (Archived)

The original tiered-hashing Step-0 pipeline (`tools/archive/ingest/run.py`) provided:
- Tiered hashing (prehash shortcuts for deduplication)
- Separate provenance tables (`audio_content`, `integrity_results`, `canonical_map`)
- Decision/artifact indexing
- Explicit outcome classification (CANONICAL, REDUNDANT, REACQUIRE, TRASH)

This functionality was superseded by the simpler, faster `tools/integrity/scan.py` + `tools/decide/recommend.py` workflow.

### Original CLI usage (archived)

```
python tools/archive/ingest/run.py scan \
  --inputs /Volumes/recovery_source_1 /Volumes/recovery_source_2 ~/Downloads/flac \
  --canonical-root /Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY \
  --quarantine-root /Volumes/RECOVERY_TARGET/Root/QUARANTINE \
  --db artifacts/db/music.db \
  --library-tag recovery-2025-01 \
  --zone recovery \
  --strict-integrity \
  --progress
```

### Database additions

Step-0 adds additive tables for audio content, integrity results, identity hints,
canonical mapping, reacquire manifests, and scan events. Step-0 also records
file-level provenance, tiered hashes, decisions, and artifact indexing. These are
designed to be idempotent and safe to re-run.

### Hash strategy

* **Tier 1 (pre-hash)**: SHA-256 over file size + first N MB (default 4 MB).
* **Tier 2 (full hash)**: SHA-256 over full file contents.
* **Tier 3 (audio-normalized)**: reserved for future PCM-level hashing.

Hashes are stored with coverage metadata (`partial` or `full`) and the active
strategy label (`tiered-sha256-v1`) per scanned file.

### Example outputs

* `docs/examples/step0_plan.json`
* `docs/examples/reacquire_manifest.csv`
