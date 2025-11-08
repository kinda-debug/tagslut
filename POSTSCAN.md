# POST-SCAN: full step-by-step workflow

This document collects a comprehensive, prescriptive workflow for what to do
after running the initial `flac_scan.py` scan. It covers creating playlists
(M3U) for broken and candidate files, repairing files safely, verifying
repaired results, reintegrating repaired files into your library, performing
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

8) Produce a dedupe report (dry-run) and inspect

```bash
python3 scripts/flac_dedupe.py --root "$ROOT" --dry-run --verbose --trash-dir "$ROOT/_TRASH_DUPES_preview"
REPORT=$(ls -1 "$ROOT"/_DEDUP_REPORT_*.csv | tail -n1)
echo "Report: $REPORT"
head -n 20 "$REPORT"
```

9) Create an M3U of duplicate losers for inspection or pre-repair

```bash
python3 - <<'PY'
import csv,sys
report=sys.argv[1]; out=sys.argv[2]
with open(report,newline='',encoding='utf-8') as fh:
    r=csv.DictReader(fh)
    with open(out,'w',encoding='utf-8') as o:
        for row in r:
            if row.get('keep')=='no':
                o.write(row.get('path','') + '\n')
print('WROTE', out)
PY "$REPORT" duplicates_losers.m3u
wc -l duplicates_losers.m3u
```

Repair losers first (optional), then rerun dedupe if some losers are corrupt.

10) Commit dedupe (move losers to trash) — only after careful review

```bash
python3 scripts/flac_dedupe.py --root "$ROOT" --commit --trash-dir "$ROOT/_TRASH_DUPES" --verbose
```

This moves files into `$ROOT/_TRASH_DUPES/` and writes a CSV report. Check
`_DEDUP_MOVE_ERRORS.txt` if any moves failed.

11) Verify after commit

```bash
python3 scripts/flac_scan.py --root "$ROOT" --workers 4 --recompute --verbose
python3 scripts/flac_dedupe.py --root "$ROOT" --dry-run --verbose
ls -R "$ROOT/_TRASH_DUPES" | head
```

12) Quarantine (frozen) files

- Files automatically quarantined during freeze detection are moved to
  `$ROOT/_BROKEN` when `--auto-quarantine` is enabled on scan.
- Inspect and repair these files using the same `flac_repair.py` flow.

13) Backups & rollback

- Backups taken by repair (when using `--overwrite --backup-dir`) live in
  your specified backup directory — restore by copying backups back in place.
- Restore moved dupes from `_TRASH_DUPES` by moving them back to their
  original location.
- Restore DB if necessary:

```bash
cp "$ROOT/_DEDUP_INDEX.db.bak.TIMESTAMP" "$ROOT/_DEDUP_INDEX.db"
```

14) Useful sqlite queries

- List unhealthy files:

```bash
sqlite3 -batch "$ROOT/_DEDUP_INDEX.db" "SELECT path, health_note FROM files WHERE healthy=0 ORDER BY path LIMIT 200;"
```

- Count fingerprinted files:

```bash
sqlite3 -batch "$ROOT/_DEDUP_INDEX.db" "SELECT count(*) from files WHERE fingerprint_hash IS NOT NULL;"
```

15) Automation example

See `scripts/automate_postscan.sh` (included in this repo) for a safe,
interactive wrapper that runs the conservative pipeline and prompts before
making destructive changes.

16) Freeze detector & pkill behavior

- The watcher prefers targeted kills for tracked ffmpeg process groups and
  falls back to `pkill -TERM` then `pkill -KILL` (or `killall`) when needed.
- `flac_scan.py`, `flac_dedupe.py`, and `flac_repair.py` start the
  watchdog/freeze detector so ffmpeg processes spawned by these scripts are
  targeted for termination when frozen.

17) Troubleshooting

- If a scan hangs, inspect `$ROOT/_DEDUP_SCAN_LOG.txt` and diagnostics under
  the diagnostic root (see `--diagnostic-root`).
- For repair failures, inspect `$REPAIRED/logs/*_attempt*.stderr.log`.
- For unexpected moves, check `_DEDUP_MOVE_ERRORS.txt` and the dedupe CSV
  reports for context.

Final safety checklist
- DB backup created
- dedupe dry-run completed and reviewed
- rsync dry-run reviewed before writing
- backups configured if using `--overwrite`

If you want this to be committed as `POSTSCAN.md` in the repo, it is now
present (committed). Use it as the canonical post-scan workflow. If you want
changes, tell me what to add or emphasize and I’ll update the file.
