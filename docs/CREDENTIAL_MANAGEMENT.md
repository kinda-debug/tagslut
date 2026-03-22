# Credential Management

tagslut stores provider credentials in:

`~/.config/tagslut/tokens.json`

Initialize the file with:

`tagslut auth init`

Provider setup:

- TIDAL: run `tagslut auth login tidal`
  - Uses device flow
  - Refresh token is stored in `tokens.json`
  - Access tokens auto-refresh when needed

- Beatport: run `tagslut auth login beatport`
  - Paste the JWT from `dj.beatport.com` DevTools
  - Token lifetime is typically about 1 hour
  - No automatic refresh for browser JWT tokens
  - Re-paste a fresh token when expired

Check current auth state with:

`tagslut auth status`

Shell scripts should obtain tokens with:

`tagslut auth token-get beatport`

Precedence rule:

- `tokens.json` is the source of truth
- Environment variables are fallback only
- If an environment variable is used, a warning is logged
- Do not keep `BEATPORT_ACCESS_TOKEN` set permanently in your shell profile

Postman:

- Postman environment variables are for API testing only
- They are not a source of truth
- Copy the token from `tokens.json` manually when needed for Postman

Rotating a Beatport token:

- Run `tagslut auth login beatport` and paste a new token
- Or edit `~/.config/tagslut/tokens.json` directly
