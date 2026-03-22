# tagslut — Credential & Token Management Audit

<!-- Status: Active. Written 2026-03-22. See ROADMAP.md §18 for implementation plan. -->
<!-- Source: External audit report, March 22, 2026 -->

**Date**: March 22, 2026
**Status**: Two parallel systems, both partially baked — consolidation planned in §18

---

## Executive Summary

Two credential management systems operating in parallel:

1. **System A: Legacy Shell-based (`env_exports.sh` pattern)**
   Status: DEPRECATED but still partially active in shell scripts.

2. **System B: Python TokenManager (tokens.json)**
   Status: MODERN and semi-active. Correct approach, incomplete adoption.

Critical issue: `beatport.py` checks `os.getenv("BEATPORT_ACCESS_TOKEN")` first,
meaning a stale env var silently wins over a fresh token in tokens.json.

See ROADMAP.md §18 for the full consolidation plan.

---

## System A: Legacy Shell-based

Location: `docs/archive/decommission-2026-02-15/legacy-scripts/env_exports.sh`
(Archived, but still referenced by active scripts)

Scripts still using System A:
- `tagslut/metadata/beatport_harvest_catalog_track.sh`
- `tagslut/metadata/beatport_harvest_my_tracks.sh`
- `tools/beatport_import_my_tracks.py` (docstring)

---

## System B: Python TokenManager

Location:
- `tagslut/metadata/auth.py` — TokenManager class
- `tagslut/cli/commands/auth.py` — CLI commands
- `~/.config/tagslut/tokens.json` — token storage

### tokens.json structure

```json
{
  "tidal": {
    "access_token": "...",
    "refresh_token": "...",
    "expires_at": 1769434230,
    "user_id": "206516450",
    "country_code": "SE"
  },
  "beatport": {
    "access_token": "eyJ0eXAi...",
    "expires_at": 1769381654,
    "token_type": "Bearer"
  },
  "spotify": {
    "client_id": "...",
    "client_secret": "..."
  },
  "qobuz": {
    "email": "...",
    "password_md5": "..."
  }
}
```

### CLI workflow

```bash
tagslut auth init          # create empty tokens.json
tagslut auth login tidal   # device flow — stores refresh_token
tagslut auth login beatport # paste JWT from DevTools — stores access_token
tagslut auth status        # shows configured providers, auto-refreshes
```

### Embedded public credentials

Three public credentials are base64-encoded in `auth.py` (lines 50, 66).
These are NOT secrets — extracted from public applications (tiddl project,
dj.beatport.com DevTools). Widely available in open-source code.

---

## Precedence problem

Current code in `beatport.py`:
```python
token = os.getenv("BEATPORT_ACCESS_TOKEN") or \
        (token.access_token if token_mgr.get_token("beatport") else None)
```

Env var wins. If operator has a stale BEATPORT_ACCESS_TOKEN in their shell
environment from a previous session, it silently overrides the fresh token
in tokens.json. No warning is logged. No documentation of this behavior exists.

Fix: reverse the check — tokens.json first, env var as fallback with warning log.

---

## Refresh asymmetry

| Provider | Refresh | Notes |
|---|---|---|
| TIDAL | Automatic via PKCE | Works correctly |
| Beatport | None | 1-hour JWT, manual re-paste required |
| Spotify | Manual | Client credentials flow |
| Qobuz | None implemented | Password stored directly |

---

## Cross-reference matrix

| Component | System A | System B | Env Var |
|---|---|---|---|
| Python CLI (auth) | ✗ | ✓ | Fallback |
| Metadata providers (TIDAL) | ✗ | ✓ | ✗ |
| Metadata providers (Beatport) | ⚠ | ✓ | **Wins** |
| Harvest shell scripts | ✓ | ✗ | ✓ |
| Postman collection | ✗ | ✗ | ✓ |

---

## Open questions for operator

1. Should `BEATPORT_ACCESS_TOKEN` env var remain as fallback or be removed?
2. Should Postman token sync be automated or manual?
3. Qobuz email+password in tokens.json — acceptable or switch to API key?
4. Does Beatport OAuth 2.0 support refresh grants?
