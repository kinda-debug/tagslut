# Recovery Workflow

This workflow makes scan state explicit, resumable, and auditable. It assumes macOS paths and a single authoritative SQLite DB.

## DB Path Resolution (No Ambiguity)

Resolution order (highest to lowest):
1) `--db` CLI flag
2) `DEDUPE_DB` environment variable
3) `db.path` in `config.toml`

Use the resolver tool to confirm what will be used:

```bash
python3 tools/db/resolve_db_path.py --db /path/to/music.db
```

Guardrail: writing to a DB under the repo root is blocked unless you pass `--allow-repo-db`.

## Phases (Commands)

Assume:

```bash
export DEDUPE_DB=~/Projects/dedupe_db/music.db
ROOT=/Volumes/RECOVERY_TARGET/Root/FINAL_LIBRARY
LIB=recovery
ZONE=accepted
```

1) Fast scan (metadata + STREAMINFO)

```bash
python3 tools/integrity/scan.py "$ROOT" \
  --library "$LIB" \
  --zone "$ZONE" \
  --no-check-integrity \
  --no-check-hash
```

2) Integrity scan (missing/stale/failed only)

```bash
python3 tools/integrity/scan.py "$ROOT" \
  --library "$LIB" \
  --zone "$ZONE" \
  --check-integrity
```

3) Hashing scan (missing/stale only)

```bash
python3 tools/integrity/scan.py "$ROOT" \
  --library "$LIB" \
  --zone "$ZONE" \
  --check-hash
```

To force a full rescan, add `--force-all` (use sparingly).

4) Duplicate recommendation

```bash
python3 tools/decide/recommend.py --db "$DEDUPE_DB" --output plan.json
```

5) Apply plan (dry-run first)

```bash
python3 tools/decide/apply.py plan.json --dry-run
python3 tools/decide/apply.py plan.json --execute
```

6) Post-apply verify winners (paths-from-file mode)

```bash
python3 tools/integrity/scan.py \
  --paths-from-file winners.txt \
  --check-integrity \
  --check-hash
```

## Freeze a DB Copy Safely

Preferred (SQLite backup):

```bash
sqlite3 "$DEDUPE_DB" ".backup 'music.db.frozen'"
```

Alternative (filesystem copy when idle):

```bash
cp -a "$DEDUPE_DB" "music.db.frozen"
```

## Compare Two DBs

Use the doctor tool on each DB and compare the summaries:

```bash
python3 tools/db/doctor.py --db /path/to/db_one.db
python3 tools/db/doctor.py --db /path/to/db_two.db
```

If you need stale integrity counts:

```bash
python3 tools/db/doctor.py --db /path/to/db_one.db --stale-days 30
```

## Updated Plan

- Treat `integrity_checked_at` and `sha256_checked_at` as the source of truth; legacy rows without timestamps are considered missing.
- Default scans are incremental: unchanged files with required results are skipped unless `--force-all` is explicitly set.
- Every scan creates a session record and per-file run history so the operator can prove what ran, when, and with which flags.
