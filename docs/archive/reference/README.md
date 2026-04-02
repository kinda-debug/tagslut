# Reference Files (Local Only)

This directory and the repo root contain local-only reference files used during provider development.
These files are **never committed** to version control and are listed in `.gitignore`.

## Security-sensitive files

| File | Contents | Handling |
|---|---|---|
| `tidalhar.txt` | Browser HAR capture with TIDAL request/response traces, auth headers, bearer tokens | Rotate tokens if still valid. Do not share. |
| `auth.txt` | TIDAL login page HTML with client-side bootstrap config | Reference only. |
| `tidal_tokens.json` / `tidal_tokens.txt` | TIDAL OAuth PKCE tokens (access + refresh) | Rotate after use. Never commit. |
| `cff5a0f2f4c9b1545d5d.js` | Beatport web bundle exposing OAuth flow (token, refresh, introspect, revoke), CLIENT_ID, CLIENT_SECRET references | Likely public bundle constants, but treat as sensitive. |

## API reference files

| File | Contents | Purpose |
|---|---|---|
| `tidal-api-oas.json` | TIDAL OpenAPI v2 spec (207 paths, version 1.3.2) | Endpoint/resource contract reference for provider development |
| `beatport-v3.json` | Beatport v4 catalog API spec (117 paths) | Catalog + ISRC endpoint reference |
| `beatport-search.json` | Beatport search service spec (7 paths) | Search endpoint reference |

## Policy

These files exist locally for development only. They inform provider wrapper design, auth flow implementation, and endpoint selection. They must never be committed, pushed, or included in backups without sanitization.

If you need information from these files for provider work, extract the relevant endpoint patterns or auth flow descriptions into code comments or contract docs -- not the raw files themselves.
