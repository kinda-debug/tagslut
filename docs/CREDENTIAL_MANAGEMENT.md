# Credential Management

## Purpose

This document defines the Phase 1 credential source of truth for `tagslut` and the
current operator workflow for provider tokens.

## Source Of Truth

Primary source of truth: `TokenManager` backed by `~/.config/tagslut/tokens.json`

- File location: `~/.config/tagslut/tokens.json`
- Create or inspect it with `poetry run tagslut auth init` and `poetry run tagslut auth status`
- Store active provider tokens here first
- Treat shell environment variables as fallback-only where they still exist

`tokens.json` wins over legacy environment variables in the active Beatport provider path.

## Provider Activation Policy (Optional)

Metadata provider activation can be controlled via `~/.config/tagslut/providers.toml` (optional).

- If the file is missing, defaults remain unchanged: Beatport + TIDAL are enabled.
- If present, providers with `metadata_enabled = false` are filtered out before enrichment.

Supported keys (Phase 1):

```toml
[providers.beatport]
metadata_enabled = true
trust = "secondary" # "dj_primary" | "secondary" | "do_not_use_for_canonical"

[providers.tidal]
metadata_enabled = true
trust = "secondary"
```

## Current Provider Scope

Current authenticated provider flows visible in repo code are:

- Beatport
- Tidal

This Phase 1 patch does not introduce new provider auth flows beyond those current surfaces.

## Provider Setup

### Beatport

Use `tokens.json` first.

1. Run `poetry run tagslut auth init` once if `~/.config/tagslut/tokens.json` does not exist.
2. Run `poetry run tagslut auth login beatport`.
3. Paste the current Beatport bearer token from `dj.beatport.com` DevTools when prompted.
4. Verify with `poetry run tagslut auth status`.

Shell usage:

```bash
poetry run tagslut token-get beatport
```

Fallback behavior:

- `BEATPORT_ACCESS_TOKEN` still works in Phase 1 only as a fallback
- if that fallback is used in the active Beatport provider path, a warning is logged
- stale `BEATPORT_ACCESS_TOKEN` values can still confuse shell sessions and Postman if you keep exporting them

### Tidal

Use `tokens.json`.

1. Run `poetry run tagslut auth init` once if needed.
2. Run `poetry run tagslut auth login tidal`.
3. Complete the browser/device flow.
4. Verify with `poetry run tagslut auth status`.

Shell usage:

```bash
poetry run tagslut token-get tidal
```

Tidal refresh remains managed through the existing `TokenManager` refresh path.

## Auth Command Behavior

### `tagslut auth login <provider>`

Interactively authenticates with the given provider.

- If a valid, non-expired token already exists, exits early with a message. Use `--force` / `-f` to re-authenticate anyway.
- Supported providers: `tidal`, `beatport`.

```bash
# Normal login (skips if already authenticated)
poetry run tagslut auth login tidal

# Force re-authentication
poetry run tagslut auth login tidal --force
```

### `tagslut auth logout <provider>`

Clears stored credentials for a provider.

- **tidal**: performs a best-effort server-side token revocation, then always clears local state.
- **beatport**: clears local token state only (no server-side revocation).

```bash
poetry run tagslut auth logout tidal
poetry run tagslut auth logout beatport
```

### `tagslut auth refresh <provider>`

Refreshes the access token for a provider using the stored refresh token or client credentials.

```bash
poetry run tagslut auth refresh tidal
poetry run tagslut auth refresh beatport
```

## Precedence Rules

Primary:

- `TokenManager`
- `~/.config/tagslut/tokens.json`

Fallback:

- environment variables only where still supported by the current code path
- in this Phase 1 patch, `BEATPORT_ACCESS_TOKEN` remains a fallback for Beatport search bearer auth

If `tokens.json` already has a usable Beatport token, that token is used before `BEATPORT_ACCESS_TOKEN`.

## Postman

Postman is an integration and testing consumer only. It is not the credential source of truth.

- keep the authoritative token in `~/.config/tagslut/tokens.json`
- sync Postman manually from `tagslut token-get <provider>` when needed
- do not treat Postman environment values as canonical

## Shell And Script Usage

Use the top-level shell-oriented command:

```bash
poetry run tagslut token-get beatport
poetry run tagslut token-get tidal
```

Behavior:

- success: prints only the token value on stdout
- missing token: exits non-zero and prints the error to stderr

The existing `poetry run tagslut auth token-get <provider>` command remains available, but
`poetry run tagslut token-get <provider>` is the Phase 1 shell entrypoint.

## Operator Notes

- If you still export old credential env vars in your shell profile, remove or update them.
- After this patch, the active Beatport provider path prefers `tokens.json`, but legacy env vars
  can still affect older scripts that have not yet been migrated.
- Keep `tokens.json` current, then pull tokens into shell consumers explicitly with `token-get`.

## Current Limitations

- Phase 1 does not migrate legacy shell scripts off env vars.
- Beatport token refresh is still not implemented here.
- Postman sync remains manual.
- This patch does not redesign Qobuz, Spotify, or other non-active auth surfaces.
