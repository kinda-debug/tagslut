# Session Report — 2026-04-01

**Branch:** `dev` | **DB:** `FRESH_2026/music_v3.db`

---

## Work completed this session

### Commits pushed (5 unpushed to origin at session end)

| Hash | Scope | Description |
|------|-------|-------------|
| `31d3fec` | qobuz | Extract genre from `album.genre.name` in `_normalize_track` — was always `None` |
| `4106444` | auth | Bidirectional Qobuz token sync between tagslut `tokens.json` and streamrip `dev_config.toml` |
| `5f04481` | beatport | Sync tokens from `beatportdl-credentials.json`; use beatportdl's `client_id` (`ryZ8...`) for refresh |
| `c251cf9` | prompts | Add `beatport-circuit-breaker.prompt.md` |
| `ecc1cd0` | registry | Add `qobuz` to `DEFAULT_ACTIVE_PROVIDERS` and `enabled` check in `resolve_active_metadata_providers` |

Plus earlier in session (already upstream or same-session commits):

| Hash | Scope | Description |
|------|-------|-------------|
| `28eec05` | db_writer | Fix `library_track_key` → `identity_key` column resolution; remove unused progress_callback |
| `6e39c8b` | qobuz | Target `dev_config.toml` for streamrip sync; pass `--config` to `rip`; fix download root path |
| `73687d8` | prescan | Pre-scan tag completion for `--no-download` mode (Codex, verified 3/3 tests passing) |
| `9b7353d` | ux | Per-track progress lines `[N/total] Artist - Title ✓/~/✗` in `ts-enrich` output |

### Bugs fixed

**Beatport:**
- Circuit-breaker: after first 401, provider marks itself dead for the session — no more 4 WARNING lines × N tracks
- Token sync from `beatportdl-credentials.json` — tagslut was using wrong `client_id` causing all refresh attempts to 400. Now uses beatportdl's `clientId` (`ryZ8LuyQVPqbK2mBX2Hwt4qSMtnWuTYSqBPO92yQ`) and syncs access+refresh tokens from beatportdl's credentials file on every `ts-auth beatport` call

**Qobuz:**
- `DEFAULT_ACTIVE_PROVIDERS` didn't include `qobuz` — provider was never activated despite `providers.toml` enabling it
- `resolve_active_metadata_providers` had no `cfg.qobuz.metadata_enabled` check — added
- `providers.toml` at `config/providers.toml` wasn't being loaded — default XDG path (`~/.config/tagslut/providers.toml`) was used; file was missing. Copied to correct location.
- `_normalize_track` never extracted genre — `album.genre.name` exists in track search responses but was not mapped. Fixed.
- `tools/auth qobuz` was one-way (tagslut → streamrip). Made bidirectional: pulls fresher token from streamrip if tagslut's is stale

**streamrip integration:**
- `tools/get` was calling `rip url` without `--config`, using default config instead of `dev_config.toml`
- Download root mismatch: code pointed at `/Volumes/MUSIC/mdl/StreamripDownloads`, actual is `/Volumes/MUSIC/mdldev/StreamripDownloads`

---

## DB state at session end

| Metric | Count |
|--------|-------|
| Total track_identity rows | 620 |
| Has BPM | 472 |
| Has key | 141 |
| Has genre | 140 |
| Has label | 140 |
| Unenriched (enriched_at IS NULL) | 450 |

Genre/label coverage is low (140/620 = 23%) because:
1. The 450 unenriched tracks haven't been processed yet
2. The Qobuz fix (`31d3fec`) was committed at end of session — not yet applied to the DB
3. Qobuz `user_auth_token` expired mid-session; required manual re-login

---

## Open issues for next session

### P0 — Blocks daily enrichment

**Qobuz token expiry is fully manual.** `tools/auth qobuz` only refreshes app credentials (`app_id`/`app_secret`). The `user_auth_token` has no auto-refresh path — Qobuz has no refresh token mechanism, only full re-login. When the session expires (unknown TTL, empirically ~hours to days), enrichment silently returns `Genre: 0`. The only signal is checking `ts-enrich` output for `Genre: 0`. Fix: add token validity check to `tools/auth qobuz` — if `user/get` returns 401, trigger interactive re-login automatically.

### P1 — Enrichment UX

**`ts-enrich` re-runs the same 100 files every time.** Mode `Retry (files with no previous match)` re-processes all files where `metadata_health_reason = 'no_provider_match'` — but tracks that got TIDAL-only enrichment (BPM+key, no genre/label) are also considered incomplete and re-queued. After `31d3fec` these will now get genre/label on the next run and settle. But the broader issue: `ts-enrich` has no `--provider` flag. You can't say "run only Qobuz against the undertagged tracks". Every run hits all three providers for every eligible file.

Prompt needed: **`enrich-provider-filter.prompt.md`** — add `--provider tidal|beatport|qobuz` to `tagslut index enrich` and `tools/enrich`, so a single-provider pass is possible.

**`ts-enrich` starts at file 1 every time.** Resumability is per-session only (Ctrl+C then re-run). There's no persistent cursor. If interrupted, the next run re-scans all eligible files from the top. For a 450-file backlog hitting rate limits this is painful. The `--retry-no-match` flag selects a fixed 100-file window — not a proper cursor.

### P2 — Streamrip integration

**Streamrip downloads already have genre/label tags** (from streamrip's own enrichment). Files at `/Volumes/MUSIC/mdldev/StreamripDownloads` are tagged by streamrip before tagslut ever sees them. The `ts-get <qobuz_url>` pipeline should read existing tags from the downloaded files and write them straight to the DB — not re-query the API. Current flow re-enriches via API, wasting quota and rate limit.

Fix: add a `--read-tags-from-files` mode to `tagslut index register` that reads FLAC tags (genre, label, BPM, key, ISRC) and writes them directly to `track_identity` without API calls.

### P3 — Schema noise

**`no such column: service`** on every `db_writer.py` source snapshot write. Non-fatal, caught and logged at DEBUG, but pollutes logs. The `library_track_sources` table is missing a `service` column that the writer expects. Migration or column-name fix needed.

### P4 — Repo cleanup

`.github/prompts/repo-cleanup-supplement.prompt.md` — five-phase cleanup (safe deletions, deduplication, `files/` directory, gitignore, structural bug docs). Operator-only, not delegated to Codex. Not started.

---

## Active prompt files (ready for Codex)

| File | Status | Notes |
|------|--------|-------|
| `beatport-circuit-breaker.prompt.md` | ✅ Written, not yet run | Codex task |
| `get-no-download-pre-scan.prompt.md` | ✅ Done (`73687d8`) | Complete |
| `tidal-auth-unification.prompt.md` | ✅ Done (in `auth.py`) | Complete |
| `pipeline-output-ux.prompt.md` | ✅ Done (`9b7353d`) | Complete |
| `dj-pipeline-hardening.prompt.md` | ⏸ Blocked | Pending after Phase 1 PRs |
| `repo-cleanup-supplement.prompt.md` | ⏸ Operator-only | Not delegated |

---

## Token state at session end

| Provider | Status |
|----------|--------|
| TIDAL | Valid ~3h (via tiddl) |
| Beatport | Valid ~598min (synced from beatportdl) |
| Qobuz app_id/secret | Valid (auto-refreshed from bundle) |
| Qobuz user_auth_token | Fresh (manual re-login at ~15:39) — unknown TTL |

---

## Commands reference

```bash
ts-auth              # refresh all tokens (tidal, beatport, qobuz app creds)
ts-enrich            # run hoarding enrichment against FRESH DB
ts-get <url>         # download: routes tidal→tiddl, qobuz→streamrip
ts-get <url> --dj    # download + write dj_pool.m3u files

# Manual re-auth when Qobuz session expires:
cd ~/Projects/tagslut && poetry run python -m tagslut auth login qobuz --email EMAIL --force
```
