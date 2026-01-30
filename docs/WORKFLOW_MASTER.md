# Master Dedupe Workflow (the single source of truth)

This is **the one Markdown doc** that collects every step you currently need:
· environment setup (`.env`)
· zones
· scanning
· recovery
· dedupe plan
· metadata/enrichment
· API tokens
· personal notes for `/Volumes/DJSSD/DRPBX`

Link it from `docs/WORKFLOW_METADATA.md`, `docs/WORKFLOW_PERSONAL.md`, or wherever else keeps it discoverable.

## 0. Source of truth: `.env`

1. Copy `.env.example` → `.env` once, then edit the values (DB path, volume aliases, artifacts). Example shortcuts:
   ```bash
   cd /Users/georgeskhawam/Projects/dedupe
   cp .env.example .env
   mkdir -p "$(dirname "$(jq -r '.DEDUPE_DB' .env)")"  # ensures epoch folder exists
   ```
   (You can also set `DEDUPE_DB` explicitly per epoch before running.)
2. Set the two key vars:
   - `DEDUPE_DB` → `/Users/georgeskhawam/Projects/dedupe_db/EPOCH_2026-01-29/music.db` (change the date for each run).
   - `DEDUPE_ZONES_CONFIG` → `~/.config/dedupe/zones.yaml`.
3. Source the file before every session:
   ```bash
   cd /Users/georgeskhawam/Projects/dedupe
   source .env
   ```
4. Optional: add `source /Users/georgeskhawam/Projects/dedupe/.env` to your shell profile for convenience.

> `.env` > `config.toml` for CLI defaults. Every command uses the `.env` path first.

## 1. Zones Setup (required)

1. Copy the example YAML:
   ```bash
   mkdir -p ~/.config/dedupe
   cp config.example.yaml ~/.config/dedupe/zones.yaml
   ```
2. Edit `zones.yaml` so `accepted`, `staging`, `suspect`, `quarantine` cover `/Volumes/DJSSD/…`.
3. Verify with `dedupe show-zone /Volumes/DJSSD/DRPBX/some.flac --zones-config ~/.config/dedupe/zones.yaml`.

## 2. Token/API Setup (central auth reference)

1. `dedupe metadata auth-init` → writes `~/.config/dedupe/tokens.json` with placeholders and basic structure.
2. `dedupe metadata auth-status` → run before every enrichment. It refreshes Spotify/Beatport/Tidal automatically and shows missing providers.
3. `dedupe metadata auth-login tidal` → starts the device auth dance (opens browser; copy/paste code).
4. `dedupe metadata auth-login qobuz` → prompts for email/password and writes `user_auth_token`.
5. Manual: edit `~/.config/dedupe/tokens.json` to add Spotify/Beatport client_id + client_secret, then rerun `auth-status` to refresh tokens.
6. Optional one-off refresh commands (use if tokens expire before a run):
   ```
   dedupe metadata auth-refresh spotify
   dedupe metadata auth-refresh beatport
   dedupe metadata auth-refresh tidal
   ```
7. Optional utilities (rare):
   - `dedupe/metadata/spotify_partner_tokens.py`
   - `dedupe/metadata/spotify_harvest_utils.py`

Tokens are stored in `tokens.json`; edit only the credentials (client IDs/secrets) or run the CLI logins.

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

Check stats:
```
sqlite3 "$DEDUPE_DB" "SELECT library, COUNT(*) FROM files GROUP BY library;"
```

## 4. Dedupe plan (requires zones)

```
dedupe recommend --db "$DEDUPE_DB" --output plan.json
dedupe apply plan.json --confirm
```

If `recommend` finds 0 groups, rerun `dedupe metadata auth-status` (tokens) and ensure `zones.yaml` covers `/Volumes/DJSSD`.

## 5. Recovery (if corrupt/recoverable files)

```bash
dedupe recover /Volumes/DJSSD/DRPBX \
  --db "$DEDUPE_DB" \
  --backup-dir /Volumes/DJSSD/_work/backups \
  --output recovery_report.csv \
  --execute \
  --workers 4
```

## 6. Metadata enrichment

- Recovery mode (duration health):
  ```
  dedupe metadata enrich --db "$DEDUPE_DB" --recovery \
    --providers spotify,beatport \
    --zones accepted,staging \
    --execute --verbose
  ```
- Hoarding mode (full metadata):
  ```
  dedupe metadata enrich --db "$DEDUPE_DB" --hoarding \
    --providers spotify,beatport,qobuz \
    --zones accepted \
    --execute --verbose
  ```

Use `dedupe enrich-file` for manual fixes.

## 7. Promote

```
dedupe promote /Volumes/DJSSD/_work/staging /Volumes/DJSSD/Library --execute
```
Add `--move` if you want to delete backups after promoting.

## 8. Reference links
- `docs/WORKFLOW_METADATA.md` – the generic metadata workflow.
- `docs/WORKFLOW_PERSONAL.md` – this exact workflow you just ran.
- `docs/METADATA_AUTH_RESOURCES.md` – token/CLI reference.

Keep this doc bookmarked; edit it before anything else.
