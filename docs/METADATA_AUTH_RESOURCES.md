# Metadata API & Token Resources

This reference collects every CLI/API task related to provider credentials, tokens, and harvesting so you always know where to look.

## Token Manager (central source)
- `dedupe/metadata/auth.py` → `TokenManager` reads/writes `~/.config/dedupe/tokens.json`, refreshes Spotify/Beatport/Tidal, and exposes `get_token(provider)` for the enrichment workflow.
- Always edit tokens via CLI helpers or by manually editing the JSON (only the config values, not the access tokens).

## CLI commands
- `dedupe metadata auth-init` → creates `~/.config/dedupe/tokens.json` with placeholders for every provider (Spotify, Beatport, Tidal, Qobuz). Run once per machine.
- `dedupe metadata auth-status` → shows which tokens are present/configured, triggers refresh for Spotify/Beatport/Tidal, and prints guidance for missing providers.
- `dedupe metadata auth-login tidal` → starts the device authorization flow (opens browser, polls `TokenManager` until token arrives).
- `dedupe metadata auth-login qobuz` → prompts for email/password and stores `user_auth_token`.  
- `dedupe metadata auth-refresh spotify|beatport|tidal` → explicitly refresh a single provider/token claim.

## Utility scripts (optional helpers)
- `dedupe/metadata/spotify_partner_tokens.py` → helper for partner-only Spotify credentials (for rare partner tokens).
- `dedupe/metadata/spotify_harvest_utils.py` → internal helper functions for vendor scraping/harvesting (not required for most flows).

## Workflow checks
1. Source `.env` so `DEDUPE_DB` & `DEDUPE_ZONES_CONFIG` are loaded.
2. Run `dedupe metadata auth-status` before an enrichment run to ensure token freshness.
3. If a provider reports “not configured,” fill in `tokens.json` via `auth-init` + manual edits, then rerun `auth-status`.

For more detail see `docs/WORKFLOW_METADATA.md` (auth section) and `docs/WORKFLOW_PERSONAL.md` (day-to-day checklist).
