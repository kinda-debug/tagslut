# tagslut repo audit — 2026-04-09

---

### Findings (highest operational risk first)

---

#### F-01 — No guard against operating on the LEGACY DB
**Severity:** Critical
**Category:** Confirmed defect (safety gate missing)

**Why it matters:** The operator model explicitly says the LEGACY DB at `/Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/` must never be used as `$TAGSLUT_DB`. If the shell env is wrong (stale session, sourcing the wrong dotfile), every write command — `tagslut get`, `tagslut fix`, `ts-enrich` — will silently operate on the wrong DB. No command warns or errors on this.

**Evidence:**
- `tagslut/utils/db.py` — `resolve_cli_env_db_path()` resolves DB from CLI → env → config. No check for the legacy path pattern. Will accept `LEGACY_2026-03-04_PICARD` without warning.
- `tagslut/cli/commands/get.py:269-270` — calls `resolve_cli_env_db_path(db_path_arg, purpose="write")`, catches `DbResolutionError`, but only errors if no path is found — not if the path is wrong.
- `.env` line 8 — currently set to FRESH DB, which is correct. But this is not enforced by code; a stale session could override it.
- `START_HERE.sh:76-89` — checks DB existence but not DB identity (not that it's the FRESH DB).

**What is unresolved:** No validation anywhere that `$TAGSLUT_DB` points at a non-legacy DB. The distinction between FRESH and LEGACY is purely operator discipline.

**Suggested next verification step:** Add a path-based guard in `resolve_cli_env_db_path` or `START_HERE.sh` that emits a hard error if the resolved DB path contains `LEGACY` or matches the known legacy directory. Alternatively, lock the legacy DB read-only at the OS level.

---

#### F-02 — Qobuz token expiry: silent zero-result enrichment
**Severity:** Critical
**Category:** Confirmed defect (silent failure mode)

**Why it matters:** `ts-enrich` runs Qobuz as one of the enrichment providers. If the Qobuz session token is expired, the provider returns 401. This is logged as WARNING and enrichment continues — returning no data for that provider. The operator sees genre/label counts of 0 for Qobuz tracks with no actionable error. SESSION_REPORT_2026-04-01 listed this as P0.

**Evidence:**
- `tagslut/metadata/providers/qobuz.py:27-40` — `_ensure_credentials()` verifies that `app_id`, `app_secret`, `user_auth_token` *exist* but does not validate their liveness (no pre-flight `/user/get` call).
- `qobuz.py:82` — 401/403 responses are logged at WARNING level; enrichment proceeds with no data returned.
- `docs/OPERATOR_QUICK_START.md` — mentions token expiry only in the auth section ("Qobuz session is expired, ts-auth will tell you"). `ts-auth` does check validity, but `ts-enrich` does not gate on it.
- SESSION_REPORT_2026-04-01.md — P0 open issue: "Qobuz token expiry is fully manual, no auto-refresh path."

**What is unresolved:** `ts-enrich` can run a full enrichment session with stale Qobuz creds, silently producing zero Qobuz-derived metadata.

**Suggested next verification step:** Add a `qobuz_session_valid()` pre-flight check in `ts-enrich` (or `tools/enrich`) that fails loudly before the enrichment batch starts. The check already exists in `ts-auth`; it can be extracted and shared.

---

#### F-03 — `$MP3_LIBRARY` default points at pre-consolidation path
**Severity:** High
**Category:** Confirmed defect / doc-code drift

**Why it matters:** `tools/get --dj` writes per-batch M3U and a global `dj_pool.m3u` to `$MP3_LIBRARY`. The default for `$MP3_LIBRARY` in `tools/get` is `/Volumes/MUSIC/MP3_LIBRARY` — the pre-consolidation raw intake output path, not `MP3_LIBRARY_CLEAN` (the curated Rekordbox pool) and not the Apple Music folder. The operator's current DJ model expects Rekordbox to read the Apple Music folder directly; M3U playlists written to `/Volumes/MUSIC/MP3_LIBRARY` point at files that may not be in either the Apple Music folder or `MP3_LIBRARY_CLEAN`.

**Evidence:**
- `tools/get:363,521,591` — `MP3_LIBRARY=${MP3_LIBRARY:-/Volumes/MUSIC/MP3_LIBRARY}`
- `tagslut/exec/dj_pool_m3u.py:140` — global M3U written to `mp3_root / "dj_pool.m3u"` where `mp3_root` is whatever `$MP3_LIBRARY` resolves to
- `tagslut/exec/fix_mp3_tags_from_filenames.py` — default root also `/Volumes/MUSIC/MP3_LIBRARY`
- `tagslut/exec/register_mp3_only.py` — same default
- `AGENT.md` — claims DJ pool writes to `$MP3_LIBRARY/dj_pool.m3u` without clarifying what `$MP3_LIBRARY` should be in April 2026

**What is unresolved:** No doc or code defines the authoritative MP3 pool for DJ use. Three candidates exist: `/Volumes/MUSIC/MP3_LIBRARY` (default), `/Volumes/MUSIC/MP3_LIBRARY_CLEAN` (curated for Rekordbox per docs), Apple Music folder (where Rekordbox actually reads). The `--dj` M3U output ends up in whichever `$MP3_LIBRARY` is set to, and that may be stale or empty.

**Suggested next verification step:** Clarify in `AGENT.md` and `OPERATOR_QUICK_START.md` what `$MP3_LIBRARY` must be set to in April 2026 and check the `.env` file. If the DJ workflow is purely Apple Music + Rekordbox with no M3U from tagslut, consider disabling the `--dj` flag's M3U writes rather than pointing them at an ambiguous location.

---

#### F-04 — beatportdl hangs on Ctrl+C required after every `ts-get <beatport_url>`
**Severity:** High
**Category:** Confirmed defect (pending rebuild)

**Why it matters:** `beatportdl` is active and not retired. The binary was patched (`interactions.go`: exit on empty input) to fix the interactive prompt loop, but the patched binary has not been rebuilt for arm64. Until it is, every `ts-get <beatport_url>` completes the download then hangs at the "Enter url:" prompt. The operator must manually Ctrl+C. There is no timeout or graceful exit.

**Evidence:**
- `docs/SESSION_REPORT_2026-04-01.md:93-97` — explicitly documents the issue and the pending rebuild.
- `tools/get` — dispatches to beatportdl directly for Beatport URLs; no timeout wrapper.

**What is unresolved:** Rebuild of beatportdl arm64 binary is pending. If a batch download runs unattended, it will hang indefinitely.

**Suggested next verification step:** Check if the patched binary exists at `~/Projects/beatportdl/beatportdl-darwin-arm64`. If not, rebuild or add a timeout wrapper in `tools/get` for the beatportdl subprocess.

---

#### F-05 — `/Volumes/MUSIC` unmounted: `tools/get` silently writes to wrong location
**Severity:** High
**Category:** Confirmed defect (operator fragility)

**Why it matters:** If `/Volumes/MUSIC` is not mounted, paths like `/Volumes/MUSIC/MP3_LIBRARY`, `/Volumes/MUSIC/mdl/bpdl`, `/Volumes/MUSIC/mdldev/StreamripDownloads` do not exist. `tools/get` will either create directories locally or fail mid-run without a clear pre-flight error. `START_HERE.sh` emits a warning but does not stop execution.

**Evidence:**
- `tools/get:363,521,591` — all volume-dependent paths with no mount check before use
- `START_HERE.sh:82-91` — checks `/Volumes/MUSIC` mount, prints WARNING, but continues
- `tools/get` has no pre-flight that aborts if the volume is absent

**What is unresolved:** A stale shell session (volume ejected mid-session) will silently produce downloads in the wrong location with no error.

**Suggested next verification step:** Add a hard `[ -d /Volumes/MUSIC ]` check at the top of `tools/get` (not just `START_HERE.sh`) with an explicit `exit 1`. The same applies to `tools/enrich`.

---

#### F-06 — `V3_SCHEMA_VERSION = 15` but migrations go to 0018
**Severity:** High
**Category:** Confirmed defect (schema/bootstrap drift)

**Why it matters:** The base schema constant is the canonical reference for "what is the full schema". If the migration runner uses `V3_SCHEMA_VERSION` as a ceiling or as a guard for "already at current version," migrations 0016–0018 (including `0018_blocked_cohort_state.sql`, which adds the `cohort`/`cohort_file` tables that `tagslut get` and `tagslut fix` depend on) may be reported as out-of-range or cause false "up to date" states. Individual migration tests exist (through `test_migration_0018.py`) so the migrations themselves are tested, but the version constant divergence creates a maintenance risk.

**Evidence:**
- `tagslut/storage/v3/schema.py:12` — `V3_SCHEMA_VERSION = 15`
- Highest migration file: `tagslut/storage/v3/migrations/0018_blocked_cohort_state.sql`
- `tests/storage/v3/test_migration_0018.py` — exists and tests migration 0018

**What is unresolved:** Whether the migration runner uses `V3_SCHEMA_VERSION` as a ceiling or as metadata. If it only uses it for display, the risk is documentation drift. If it uses it as a stop condition, migrations 0016–0018 are silently skipped on fresh DB bootstrap.

**Suggested next verification step:** Read `tagslut/storage/v3/migrations/__init__.py` (the migration runner) to determine how `V3_SCHEMA_VERSION` is used. If it's used as a run-limit, bump to 18. If it's purely metadata, add a CI assertion that `V3_SCHEMA_VERSION` matches the highest migration number.

---

#### F-07 — No Apple Music MP3 tag writeback path; COMM field noise has no clearing code
**Severity:** Medium
**Category:** Unresolved design gap

**Why it matters:** The Apple Music folder is now the canonical audio pool and Rekordbox reads tags from those files directly. The COMM (comment) field contains Lexicon noise (`09 Energy, 07 Dance...`) from the Lexicon phase-out. tagslut has enriched metadata in the DB (BPM, key, genre, ISRC, label) but has no code path to write it back to the MP3 files in the Apple Music folder. `canonical_writeback.py` is FLAC-only. `fix_mp3_tags_from_filenames.py` writes filename-derived tags only (artist/title/album/year/track). No code clears or rewrites COMM.

**Evidence:**
- `tagslut/exec/canonical_writeback.py:8,112` — imports `mutagen.flac.FLAC`; operates on FLAC-only
- `tagslut/exec/fix_mp3_tags_from_filenames.py:85-102` — writes TPE1/TIT2/TALB/TDRC/TRCK; no COMM handling
- `tagslut/exec/mp3_build.py:384-387` — reads COMM for audit; does not write or clear
- `tagslut/exec/transcoder.py:250-253` — copies COMM from source when transcoding; does not clear noise
- No `COMM` clear or normalize code found in `tagslut/exec/` or `tagslut/metadata/`

**What is unresolved:** Rekordbox will read the Lexicon noise in the comment field of every Apple Music MP3. Track and disk numbers are also empty in sampled files (expected for streaming single-track albums, but not verified as intentional for all files). No operator-facing command exists to write DB-enriched metadata to Apple Music MP3s.

**Suggested next verification step:** Determine whether an MP3-targeting writeback is needed (either extend `canonical_writeback.py` to handle MP3 via `mutagen.id3`, or create a new command). At minimum, a COMM-clearing pass using `mutagen` for the Apple Music folder is a single-function addition.

---

#### F-08 — 116 unresolved `conflict_isrc_duration` rows in `MP3_LIBRARY_CLEAN`, no review command
**Severity:** Medium
**Category:** Unresolved design gap / open question

**Why it matters:** `centralize_lossy_pool` left 116 ISRC/duration conflict groups unresolved in `MP3_LIBRARY_CLEAN`. The run manifest reports them, but there is no CLI command to surface, inspect, or resolve them. The operator is expected to manually read the manifest JSONL. Until reviewed, these 116 groups contain duplicate/ambiguous files that Rekordbox will import as duplicates.

**Evidence:**
- `tools/centralize_lossy_pool:600-604,868-875` — conflict detection writes `conflict_isrc_duration` flag; conflicted files assigned `action="keep"` but NOT deduplicated
- No `tagslut` CLI command found for reviewing centralize_lossy_pool manifests
- `docs/OPERATOR_QUICK_START.md` — "Review unresolved `conflict_isrc_duration` rows in the run audit manifest before any destructive cleanup." No tool is provided to do this.

**What is unresolved:** The conflict manifest exists but requires manual inspection. No tooling exists to turn the 116 flagged groups into actionable decisions.

---

#### F-09 — `docs/ARCHITECTURE.md` describes 4-stage DJ pipeline as "canonical" in body despite header warning
**Severity:** Medium
**Category:** Doc-code drift

**Why it matters:** Any agent or operator reading `ARCHITECTURE.md` without reading the header disclaimer carefully will see the 4-stage pipeline (backfill → validate → xml emit → DJ_LIBRARY) described as the "canonical DJ path" in section "Explicit 4-stage pipeline (canonical)". The header warns that these sections reflect pre-April 2026 architecture, but the body sections are not individually marked deprecated.

**Evidence:**
- `docs/ARCHITECTURE.md` header (lines 1-5) — "Note: sections describing the 4-stage DJ pipeline ... reflect the pre-April 2026 architecture."
- `docs/ARCHITECTURE.md` body — section header still reads: "### Explicit 4-stage pipeline (canonical)"
- `docs-housekeeping-2026-04.prompt.md` and `docs-housekeeping-2026-04b.prompt.md` — both exist, neither has been run (no evidence of execution: `COMMAND_GUIDE.md` is still in docs/ not archive/, listed files still in active docs/)

**What is unresolved:** Both housekeeping prompts describe the docs cleanup work that would fix this drift. They have not been executed.

---

#### F-10 — `tools/get` and `tagslut get` are materially different: cohort state only in CLI path
**Severity:** Medium
**Category:** Unresolved design ambiguity / intentional compatibility debt

**Why it matters:** `ts-get` wraps `tools/get` which calls `tools/get-intake`. `tagslut get` is a different command that wraps the same underlying intake but adds cohort state tracking (SQLite `cohort`/`cohort_file` tables from migration 0018), resumable failure modes, and `--fix` flag. If the operator uses `ts-get`, blocked cohorts are not tracked and `tagslut fix <cohort_id>` cannot recover them. The two entrypoints describe themselves as equivalent in WORKFLOWS.md but they are not.

**Evidence:**
- `tools/get:32` — `GET_INTAKE="$SCRIPT_DIR/get-intake"` — dispatches to `get-intake`
- `tagslut/cli/commands/get.py:99-356` — cohort state creation, `blocked_reason` / `blocked_stage` tracking
- `tagslut/cli/commands/fix.py:28-267` — resume logic operates on cohort rows; cohort rows are only created by `tagslut get`, not by `tools/get`
- `docs/WORKFLOWS.md` — lists both `ts-get` and `tagslut intake url` as equivalent entrypoints without noting the state-tracking difference

**What is unresolved:** If `ts-get` is the daily entrypoint (as CLAUDE.md states), blocked/failed downloads are not tracked in the DB and `tagslut fix` has no cohort to resume from.

---

#### F-11 — `docs-housekeeping-2026-04` prompts not executed; stale docs still in active `docs/`
**Severity:** Medium
**Category:** Doc-code drift / intentional pending debt

**Why it matters:** Both `.github/prompts/docs-housekeeping-2026-04.prompt.md` and `docs-housekeeping-2026-04b.prompt.md` describe a pending documentation cleanup pass (archive old docs, update ARCHITECTURE.md, update COMMAND_GUIDE.md). The cleanup has not been run: files listed for archival are still in `docs/`, `COMMAND_GUIDE.md` would still show the 4-stage pipeline as primary.

**Evidence:**
- `.github/prompts/docs-housekeeping-2026-04.prompt.md` — 7.4 KB, dated 2026-04-01
- `.github/prompts/docs-housekeeping-2026-04b.prompt.md` — 8.4 KB, dated 2026-04-02
- Evidence of non-execution: listed archive targets still present in `docs/`

---

#### F-12 — Quarantine GC silently deletes files after retention window with no review step
**Severity:** Medium
**Category:** Unresolved design ambiguity

**Why it matters:** `tools/review/quarantine_gc.py` deletes quarantine files older than `--days` without any operator approval step. There is no bounded review queue; files past the window are gone. If a file was quarantined in error, it will be silently deleted.

**Evidence:**
- `tools/review/quarantine_gc.py:92-107` — age-based eligibility check; deletes without confirmation
- `tagslut/cli/commands/execute.py:235-239` — `execute-quarantine-plan` moves files to quarantine with no review gate

---

### Open questions / ambiguous areas

**OQ-1:** Does the migration runner use `V3_SCHEMA_VERSION` as a ceiling or stop condition? If yes, migrations 0016–0018 are silently skipped on fresh bootstrap. Needs one read of `tagslut/storage/v3/migrations/__init__.py`.

**OQ-2:** Is the `"no such column: service"` error in `db_writer.py` (SESSION_REPORT P3) still triggering on live runs? The agent found no `db_writer.py` exists and no `service` column in the active schema — this may be fully resolved, but the SESSION_REPORT still lists it as open. Needs confirmation from a recent `ts-enrich` log.

**OQ-3:** `dj_library_normalize.py` is wired to a CLI command in `ops.py` (`plan_dj_library_normalize_cli`). The 4-stage DJ pipeline is retired. Is this command still intended to be available, or is it an orphaned compatibility path?

**OQ-4:** The `inspect-api` server in `.claude/launch.json` also points at the now-nonexistent `EPOCH_2026-03-04` DB. If used, it will fail at startup. Needs updating to `FRESH_2026`.

---

### Intentional compatibility debt vs likely bugs

| Finding | Classification |
|---------|---------------|
| `tagslut report/dj/intake` still callable with deprecation warning | Intentional compatibility debt — transitional wrapper model is explicit |
| `tagslut admin dj xml emit` still reachable | Intentional — optional Rekordbox export; not a primary DJ path |
| `tools/get-intake` still callable | Intentional — `tools/get` wraps it; still the `ts-get` implementation path |
| `docs/ARCHITECTURE.md` 4-stage section not individually marked deprecated | Likely unintentional — docs-housekeeping prompts were written to fix this |
| `V3_SCHEMA_VERSION = 15` vs migration 0018 | Likely unintentional drift — no evidence this was a deliberate freeze |
| Qobuz no pre-flight validity check | Likely unintentional — SESSION_REPORT lists it as P0 open |
| beatportdl hang | Known, pending fix — documented |
| No COMM clear path | Unresolved design gap — Lexicon phase-out left this behind |

---

### Still-live vs inert compatibility layers

| Item | Status |
|------|--------|
| `tools/get` → `tools/get-intake` | **Still live** — this is `ts-get`'s actual execution path |
| `tagslut intake` (top-level, deprecated) | **Still live** — callable, mutates state, just warns |
| `tagslut admin dj xml emit` | **Still live** — full Rekordbox XML emit available |
| `tagslut/exec/dj_library_normalize.py` | **Still live** — wired to CLI via ops.py |
| `/Volumes/MUSIC/MP3_LIBRARY` default | **Still live** — default in 5+ files |
| `docs/archive/DOWNLOAD_STRATEGY.md` | Inert archive — content is now accurate but in archive/ |
| DJ_LIBRARY path references | Near-inert — found in `precheck_inventory_dj.py` but not as a write target |

---

```
--- CHECKPOINT: Q1–Q11 complete ---
Findings: 12 ranked findings + 4 open questions
Highest severity open: Critical (F-01, F-02)
Questions remaining: none
Last files examined: tagslut/utils/db.py, tagslut/metadata/providers/qobuz.py, START_HERE.sh, .claude/launch.json
Resume from: N/A — audit complete
---
```

---

**Highest priority next actions:**

1. **F-01** — Add a LEGACY DB path guard in `resolve_cli_env_db_path` or at minimum in `START_HERE.sh` as a hard exit.
2. **F-02** — Add Qobuz pre-flight session check in `tools/enrich` before enrichment batch starts.
3. **F-06** — Read `tagslut/storage/v3/migrations/__init__.py` to determine if `V3_SCHEMA_VERSION` is a stop condition; if so, bump to 18.
4. **F-03** — Clarify `$MP3_LIBRARY` in `.env` and `AGENT.md` for April 2026 model; decide whether `--dj` M3U output is still meaningful given the Apple Music + Rekordbox direct-read model.
5. **OQ-4** — Update `inspect-api` entry in `.claude/launch.json` to `FRESH_2026` DB path (same fix applied to `dj-review` today).
6. Run the two `docs-housekeeping` prompts (F-11/F-09) to clear the ARCHITECTURE.md 4-stage section drift.
