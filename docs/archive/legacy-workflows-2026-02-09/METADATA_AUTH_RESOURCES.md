# Metadata API & Token Resources

This reference collects every CLI/API task related to provider credentials, tokens, and harvesting so you always know where to look.

## Token Manager (central source)
- `tagslut/metadata/auth.py` → `TokenManager` reads/writes `~/.config/tagslut/tokens.json`, refreshes Spotify/Beatport/Tidal, and exposes `get_token(provider)` for the enrichment workflow.
- Always edit tokens via CLI helpers or by manually editing the JSON (only the config values, not the access tokens).

## Supported Providers

| Provider | Auth Type | Configuration |
|----------|-----------|---------------|
| Spotify | Client credentials | `client_id` + `client_secret` in tokens.json |
| Beatport | Bearer token or web scraping | Optional `access_token` from dj.beatport.com |
| Tidal | Device authorization | Run `auth-login tidal`, stores `refresh_token` |
| Qobuz | Email/password | Run `auth-login qobuz`, stores `user_auth_token` |
| Apple Music | Dynamic (auto-extracted) | **No configuration required** |
| iTunes | None (public API) | **No configuration required** |

## CLI commands
- `tagslut metadata auth-init` → creates `~/.config/tagslut/tokens.json` with placeholders for every provider. Run once per machine.
- `tagslut metadata auth-status` → shows which tokens are present/configured, triggers refresh for Spotify/Beatport/Tidal, and prints guidance for missing providers.
- `tagslut metadata auth-login tidal` → starts the device authorization flow (opens browser, polls `TokenManager` until token arrives).
- `tagslut metadata auth-login qobuz` → prompts for email/password and stores `user_auth_token`.
- `tagslut metadata auth-refresh spotify|beatport|tidal` → explicitly refresh a single provider/token claim.

### Apple Music (No Setup Required)
The Apple Music provider automatically extracts a bearer token from the Apple Music web application at runtime. No manual configuration is needed. It provides rich metadata including ISRC, composer, credits, lyrics, and classical metadata.

## Utility scripts (optional helpers)
- `tagslut/metadata/spotify_partner_tokens.py` → helper for partner-only Spotify credentials (for rare partner tokens).
- `tagslut/metadata/spotify_harvest_utils.py` → internal helper functions for vendor scraping/harvesting (not required for most flows).

## Workflow checks
1. Source `.env` so `TAGSLUT_DB` & `TAGSLUT_ZONES_CONFIG` are loaded.
2. Run `tagslut metadata auth-status` before an enrichment run to ensure token freshness.
3. If a provider reports “not configured,” fill in `tokens.json` via `auth-init` + manual edits, then rerun `auth-status`.

For more detail see `docs/WORKFLOW_METADATA.md` (auth section) and `docs/WORKFLOW_PERSONAL.md` (day-to-day checklist).
