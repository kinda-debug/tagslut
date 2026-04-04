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

### beatportdl rebuild pending
The beatportdl source was patched (`interactions.go`: exit on empty input) to fix
the interactive prompt loop after non-interactive use. The build requires taglib arm64
(`arch -arm64 brew install taglib` then rebuild). Until rebuilt, `ts-get <beatport_url>`
will complete the download but hang at the "Enter url" prompt — Ctrl+C to exit.

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

---

## Plan — next 2 days

### Context

The DB has 1,212 files across `accepted` (625), `suspect` (555), `staging` (32). Of those, 154 accepted and 103 suspect are missing genre. The 7 FLACs already downloaded at `/Volumes/MUSIC/mdldev/StreamripDownloads` have genre tags embedded by streamrip but those tags aren't in the DB yet. The enrichment pipeline is now fully wired (Beatport + TIDAL + Qobuz all working) but the 450 unenriched files and ~260 genre-missing files need to be processed.

---

### Day 1 — Clear the enrichment backlog

**Step 1 — Register streamrip downloads** *(manual, 5 min)*
```bash
cd ~/Projects/tagslut
source env_exports.sh
poetry run python -m tagslut index register /Volumes/MUSIC/mdldev/StreamripDownloads --source qobuz --execute
```
This writes the 7 existing Qobuz downloads into the DB. Their genre/label tags are already in the files — register reads them directly.

**Step 2 — Run full enrichment** *(ts-enrich, ~20 min)*
```bash
ts-enrich
```
With Beatport token synced from beatportdl, Qobuz freshly authenticated, and the genre fix (`31d3fec`) now in place, this pass should fill genre+label for most of the 260 undertagged tracks. Run twice if rate-limited (it's resumable).

**Step 3 — Check results**
```bash
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*), SUM(CASE WHEN canonical_genre IS NOT NULL THEN 1 ELSE 0 END) FROM track_identity;"
```
Target: genre coverage > 80% of enriched tracks.

**Step 4 — Hand `beatport-circuit-breaker.prompt.md` to Codex** *(already written)*
The prompt is at `.github/prompts/beatport-circuit-breaker.prompt.md`. Delivers: `_session_dead` flag on BeatportProvider so a dead token produces 1 WARNING instead of retry spam.

---

### Day 2 — Intake pipeline and download UX

**Problem:** `ts-get <qobuz_url>` is untested end-to-end since the `dev_config.toml` and download root fixes. The full flow (download → register → MP3 build → dj_pool.m3u) needs a real test run.

**Step 1 — Test `ts-get` with a Qobuz album**
```bash
ts-get https://open.qobuz.com/album/btjlqvi1808fc --dj
```
Expected: FLAC lands in `/Volumes/MUSIC/mdldev/StreamripDownloads`, gets registered, MP3 built in `MP3_LIBRARY`, `dj_pool.m3u` updated. Verify each step.

**Step 2 — Write `enrich-provider-filter.prompt.md`** for Codex
Adds `--provider tidal|beatport|qobuz` flag to `tagslut index enrich` and `tools/enrich`. Allows targeted single-provider passes (e.g. "just run Qobuz against the 260 genre-missing tracks") without hitting all three providers for all eligible files. This also fixes the "starts over" problem — a dedicated Qobuz-only pass runs only against tracks missing genre/label, not the full 450 unenriched set.

**Step 3 — Qobuz token auto-relogin**
Add token validity check to `tools/auth qobuz`: if `user/get` returns 401, print a clear one-liner with the re-login command rather than silently continuing. Goal: make the failure loud instead of invisible (Genre: 0 in results with no warning).

**Step 4 — Streamrip tag passthrough** *(Codex prompt)*
Files downloaded via `ts-get <qobuz_url>` already have genre/label/BPM embedded by streamrip. The register step should read those tags and write them directly to `track_identity` columns without queuing for API enrichment. Write `streamrip-tag-passthrough.prompt.md`: extend `tagslut index register --source qobuz` to read Vorbis tags (GENRE, LABEL, BPM, KEY, ISRC) from each FLAC and populate `canonical_*` columns at registration time.

---

### Backlog (not this week)

- `no such column: service` in db_writer source snapshots — non-fatal, fix when convenient
- `repo-cleanup-supplement.prompt.md` — operator-only, five phases, not delegated
- `dj-pipeline-hardening.prompt.md` — blocked until Phase 1 PRs merge
- Rekordbox: delete the 75 missing entries from the collection (manual, in Rekordbox Missing File Manager → select all → Delete)

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

---

## Clean Lossy Pool Report

Implemented and executed the new standalone operator utility:

```bash
/Users/georgeskhawam/Projects/tagslut/tools/centralize_lossy_pool
```

Production run:
- destination: `/Volumes/MUSIC/MP3_LIBRARY_CLEAN`
- archive run: `/Volumes/MUSIC/_archive_lossy_pool/MP3_LIBRARY_CLEAN_20260403_212500`

Primary execute result:
- scanned: `19716`
- kept: `11094`
- archived: `8622`
- final audit: `invalid_audio_count = 0`
- final audit: `exact_duplicate_files = 0`
- unresolved `conflict_isrc_duration`: `116` files across `44` groups

Follow-up resume run:
- a literal hidden-style directory `/Volumes/MUSIC/_work/gig_runs/...` was skipped by design because directory names beginning with `.` are excluded
- renamed it to `/Volumes/MUSIC/_work/gig_runs/_leftover_pool`
- reran the same archive stamp with `--execute --resume --verbose --limit-root _work/gig_runs/_leftover_pool`
- absorbed the remaining `67` lossy files (`53` kept, `14` archived as duplicate hash)

Final operator state:
- no `.mp3`, `.aac`, or `.m4a` files remained outside `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` and `/Volumes/MUSIC/_archive_lossy_pool/*`
- Rekordbox import should now start fresh from `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` only
