# POST-SCAN: full step-by-step workflow (archived)

> **Status:** Archived. This document captures the legacy end-to-end process that
> followed the historical `flac_scan.py` workflow. The modern toolkit now relies
> on the unified `dedupe` CLI (`scan-library`, `parse-rstudio`, `match`,
> `generate-manifest`) which supersedes the instructions below. Retain this guide
> for reference when replaying historical investigations or interpreting old
> incident reports.

This document collects a comprehensive, prescriptive workflow for what to do
after running the initial `flac_scan.py` scan. It covers creating playlists
(M3U) for broken and candidate files, repairing files safely, verifying repaired
results, reintegrating repaired files into your library, performing
deduplication (dry-run and commit), quarantine handling, backups & rollback,
automation examples, and troubleshooting.

This file is intentionally prescriptive and copy-paste friendly. Keep a
recent DB backup before running destructive steps.

Prereqs
- Work from repository root and set PYTHONPATH:

```bash
export PYTHONPATH="$(pwd)"
```

- Ensure `ffmpeg`, `fpcalc`, `flac`, and `metaflac` are installed and on PATH.
- Replace `/path/to/music` below with your real library root; we call it
  `$ROOT` in examples.

Safety first
- Always take a DB backup and prefer dry-runs and separate repaired staging
  folders before replacing originals.

```bash
cp "$ROOT/_DEDUP_INDEX.db" "$ROOT/_DEDUP_INDEX.db.bak.$(date +%s)"
```

0) Quick glossary
- DB — `$ROOT/_DEDUP_INDEX.db` created by `flac_scan.py`.
- broken playlist — an M3U listing files that failed health checks.
- REPAIRED — a temporary directory you use to hold repaired files for
  inspection before reintegration.

1) Run or re-run the scan (if needed)

```bash
python3 scripts/flac_scan.py --root "$ROOT" --workers 4 --verbose \
  --broken-playlist "$ROOT/broken_files_unrepaired.m3u"
```

This produces/updates `_DEDUP_INDEX.db` and appends broken entries to the
broken playlist when relevant.

2) Produce explicit playlists from the DB

- Broken/unhealthy files (healthy = 0):

```bash
sqlite3 -batch "$ROOT/_DEDUP_INDEX.db" "SELECT path FROM files WHERE healthy=0;" > broken_files_unrepaired.m3u
wc -l broken_files_unrepaired.m3u
head -n 10 broken_files_unrepaired.m3u
```

- Files with health notes (diagnostic candidates):

```bash
sqlite3 -batch "$ROOT/_DEDUP_INDEX.db" "SELECT path FROM files WHERE health_note IS NOT NULL AND health_note != '';" > health_noted.m3u
```

3) Repair files safely into a staging folder

Always repair into a separate folder for manual review before reintegration.

```bash
REPAIRED="/tmp/REPAIRED_$(date +%s)"
python3 scripts/flac_repair.py \
  --playlist broken_files_unrepaired.m3u \
  --output "$REPAIRED" \
  --capture-stderr \
  --ffmpeg-timeout 30
```

- `--capture-stderr` writes per-file ffmpeg stderr logs to `$REPAIRED/logs/`.
- If you prefer repairing one file at a time use `--file /path/to/file`.

4) Inspect repair results

```bash
ls -lah "$REPAIRED" | head
ls -lah "$REPAIRED/logs" | head
less "$REPAIRED/logs/<somefile>_transcode_attempt1.stderr.log"
```

If a repair failed, logs will indicate the failing ffmpeg command and stderr.

5) Re-scan repaired outputs to validate success

```bash
python3 scripts/flac_scan.py --root "$REPAIRED" --workers 4 --verbose \
  --broken-playlist "$REPAIRED/broken_after_repair.m3u"

sqlite3 -batch "$REPAIRED/_DEDUP_INDEX.db" "SELECT path, healthy, health_note FROM files ORDER BY path LIMIT 50;"
```

6) Reintegrate repaired files into the main library (choose strategy)

- Manual selective copy (recommended): preview with rsync dry-run.

```bash
rsync -avhn --progress "$REPAIRED"/ "$ROOT"/    # dry-run
# If satisfied:
rsync -avh --progress "$REPAIRED"/ "$ROOT"/
```

- Use the repair script to overwrite originals and keep backups (use only
  if you have a robust backup plan):

```bash
python3 scripts/flac_repair.py --playlist broken_files_unrepaired.m3u \
  --output "$ROOT" --capture-stderr --overwrite --backup-dir "/path/to/repair-backups"
```

7) Re-scan the main library to refresh DB

```bash
python3 scripts/flac_scan.py --root "$ROOT" --workers 4 --recompute --verbose
```
