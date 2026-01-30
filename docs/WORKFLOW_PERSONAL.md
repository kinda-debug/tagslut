# Georges’ Personal Workflow

This is a distilled, "just the commands I need" version of `docs/WORKFLOW_MASTER.md`, tuned to `/Volumes/DJSSD/DRPBX` and your current tooling. It keeps the master doc as the full blueprint while giving you a fast path to get things done each epoch.

## 0. Environment (auto-populated)

Every run begins by refreshing `.env` with the latest epoch, artifacts, and report paths:

```bash
cd /Users/georgeskhawam/Projects/dedupe
python3 scripts/auto_env.py      # updates .env with newest EPOCH_* DB + artifact/report dirs
source .env                     # exports DEDUPE_DB, DEDUPE_ZONES_CONFIG, etc.
mkdir -p "$(dirname "$DEDUPE_DB")"  # ensures the epoch folder exists
```

`python3 scripts/auto_env.py` rewrites `.env` so you never have to edit it manually; the script prints the DB it sets.

## 1. Zones (first-time / when configs move)

```bash
mkdir -p ~/.config/dedupe
cp config.example.yaml ~/.config/dedupe/zones.yaml
# edit the YAML so `accepted` includes /Volumes/DJSSD/DRPBX/Library, /Volumes/DJSSD/_work/staging, etc.
export DEDUPE_ZONES_CONFIG=~/.config/dedupe/zones.yaml
dedupe show-zone /Volumes/DJSSD/DRPBX/foo.flac --zones-config "$DEDUPE_ZONES_CONFIG"
```

The guarded `dedupe show-zone` call confirms your zones file applies to the paths you care about.

## 2. Tokens/auth (do this once per session)

```bash
dedupe metadata auth-init                      # creates ~/.config/dedupe/tokens.json
dedupe metadata auth-login tidal                # start device auth in browser
dedupe metadata auth-login qobuz                # prompts for email/password
# add Spotify/Beatport credentials manually to ~/.config/dedupe/tokens.json if needed
dedupe metadata auth-status                     # refreshes everything and reports missing providers
dedupe metadata auth-refresh spotify            # optional: force refresh
dedupe metadata auth-refresh beatport           # optional: force refresh
dedupe metadata auth-refresh tidal              # optional: force refresh (after login)
```

The `auth-status` command is the one-stop check before enrichment—run it right before `dedupe metadata enrich`.

## 3. Scan `/Volumes/DJSSD/DRPBX`

```bash
dedupe scan /Volumes/DJSSD/DRPBX \
  --db "$DEDUPE_DB" \
  --create-db \
  --check-integrity \
  --check-hash \
  --progress \
  --verbose \
  --library DRPBX
```

Quick sanity check:

```bash
sqlite3 "$DEDUPE_DB" "SELECT library, COUNT(*) FROM files GROUP BY library;"
```

## 4. Deduplication plan

```bash
dedupe recommend --db "$DEDUPE_DB" --output plan.json
dedupe apply plan.json --confirm
```

If `recommend` returns zero groups, rerun `dedupe metadata auth-status` and confirm `accepted/staging` cover your files.

## 5. Recovery (if you saw corrupt or missing metadata)

```bash
dedupe recover /Volumes/DJSSD/DRPBX \
  --db "$DEDUPE_DB" \
  --backup-dir /Volumes/DJSSD/_work/backups \
  --output recovery_report.csv \
  --execute \
  --workers 4
```

## 6. Metadata enrichment

```bash
dedupe metadata enrich \
  --db "$DEDUPE_DB" \
  --recovery \
  --zones accepted,staging \
  --providers spotify,beatport \
  --execute \
  --verbose

dedupe metadata enrich \
  --db "$DEDUPE_DB" \
  --hoarding \
  --zones accepted \
  --providers spotify,beatport,qobuz \
  --execute \
  --verbose
```

For a single file:

```bash
dedupe enrich-file --db "$DEDUPE_DB" --file /Volumes/DJSSD/DRPBX/Some.flac --providers spotify --execute
```

## 7. Promote (staging → library)

```bash
dedupe promote /Volumes/DJSSD/_work/staging /Volumes/DJSSD/Library --execute --move
```

The `--move` flag reuses the staging space so you don’t leave duplicates behind.

## Notes

- The master workflow (`docs/WORKFLOW_MASTER.md`) is still the single source of truth; use this doc when you need a concise execution plan.  
- Always run `python3 scripts/auto_env.py && source .env` at the start of a session so every command gets the right `DEDUPE_DB`.  
- If tokens seem stale, `dedupe metadata auth-status` refreshes them, and `auth-refresh ...` is there for emergencies.  
- Keep `/Volumes/DJSSD/_work/backups` for recover output and run `dedupe metadata enrich` after `dedupe scan` to capture fresh metadata.  
- This workflow assumes `DEDPE_ZONES_CONFIG` is pointing at `~/.config/dedupe/zones.yaml`; edit as needed but keep the environment variable exported before each run.
