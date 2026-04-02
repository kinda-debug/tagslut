<!-- Status: Active. Synced 2026-04-02 for ts-get/ts-enrich/ts-auth + M3U DJ pool. Legacy 4-stage pipeline is archival. -->

# Operations

Operator quick reference for the current model.

## Primary Surface (use these)
- `ts-get <url> [--dj]` — download via tiddl (TIDAL), streamrip (Qobuz), or beatportdl (Beatport); `--dj` writes per-batch + global `dj_pool.m3u`.
- `ts-enrich` — metadata hoarding pass: beatport → tidal → qobuz → reccobeats.
- `ts-auth [tidal|beatport|qobuz|all]` — refresh provider tokens; validates Qobuz session; syncs beatportdl credentials.

Compatibility shims still exist (`poetry run tagslut intake/index/...`, `tools/get`, `tools/tagslut`) but are legacy reference only.

## Environment
```bash
cd /Users/georgeskhawam/Projects/tagslut
source START_HERE.sh
```
Exports TAGSLUT_DB, MASTER_LIBRARY, MP3_LIBRARY, STAGING_ROOT, etc. Use these paths instead of manual env setup.

## Token Management
- Run `ts-auth` before downloads/enrichment.
- **Qobuz:** user_auth_token expires; when `ts-auth` reports expiry, re-login: `poetry run python -m tagslut auth login qobuz --email EMAIL --force`.
- **Beatport:** if token stale, launch `~/Projects/beatportdl/beatportdl-darwin-arm64`, exit after the prompt, then `ts-auth beatport` to sync credentials.
- **TIDAL:** `ts-auth tidal` delegates to tiddl refresh.

## DJ Pool (current)
- DJ pool is a single M3U at `$MP3_LIBRARY/dj_pool.m3u` plus per-batch M3Us written by `ts-get --dj`.
- Import `dj_pool.m3u` into Rekordbox; build crates there; sync to USB.
- `DJ_LIBRARY` folder is legacy-only; not written by current workflows.

## Enrichment
- `ts-enrich` hits beatport → tidal → qobuz → reccobeats; resumable; uses `$TAGSLUT_DB`.
- To limit to one provider, use the `--provider` flag in `tagslut index enrich` / `tools/enrich` (see docs/COMMAND_GUIDE.md).

## Legacy Reference
- 4-stage DJ pipeline (backfill/validate/XML emit) and `DJ_LIBRARY`-based flows are retired. See archived docs in `docs/archive/` only if you need historical context.
