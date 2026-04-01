# docs-housekeeping-2026-04 — Docs sync, prompt triage, and archive pass

## Do not recreate existing files. Do not modify files not listed in scope.
## Do not touch any Python source, tests, migrations, or tools/ scripts.

---

## Context

The repo went through a major architectural shift in late March–April 2026:
- The 4-stage DJ pipeline (backfill/validate/XML emit) was replaced with an M3U-based
  DJ pool model. `DJ_LIBRARY` as a separate folder is retired.
- `ts-get` / `ts-enrich` / `ts-auth` shell shortcuts replaced the old `tools/get-intake`
  daily workflow for enrichment.
- Qobuz was added as a third metadata provider (active, authenticated).
- beatportdl was restored as the explicit Beatport download path (not retired).
- The download strategy doc says "beatportdl is permanently retired" — this is now wrong.
- ROADMAP.md still shows §20 (tiddl token bridge) as NEXT — it is complete.
- COMMAND_GUIDE.md still describes the old 4-stage pipeline as the primary workflow.
- Several root-level `.md` files (Technical Whitepapers) are sitting loose in the repo root.

---

## Scope

### 1. `docs/ROADMAP.md`

Mark the following sections as COMPLETE with today's date (2026-04-01):
- §20 — tiddl → tokens.json bridge: mark COMPLETE (commit 5f04481 and earlier)
- §21 — Download strategy rewrite: mark COMPLETE (DOWNLOAD_STRATEGY.md already updated)
- §23 — Provider architecture: all 8 prompts — mark Prompts 1–7 as COMPLETE,
  note that operational Qobuz metadata is live as of 2026-04-01

Add a new section at the top of the execution order block:

```
11. Provider architecture + Qobuz metadata (§23)  ← COMPLETE (2026-04-01)
12. DJ pool M3U model — replace 4-stage pipeline  ← COMPLETE (2026-04-01)
13. beatportdl restore as explicit download path  ← COMPLETE (2026-04-01)
```

### 2. `docs/COMMAND_GUIDE.md`

Rewrite to reflect current state. The old 4-stage pipeline section should be
moved to a "Legacy reference" block at the bottom marked RETIRED.

New primary content:

**Daily workflow commands:**
```bash
ts-get <url>              # download: tidal→tiddl, qobuz→streamrip, beatport→beatportdl
ts-get <url> --dj         # download + append to dj_pool.m3u
ts-enrich                 # metadata hoarding: beatport → tidal → qobuz
ts-auth                   # refresh all provider tokens
```

**Token management:**
```bash
ts-auth tidal             # refresh TIDAL via tiddl
ts-auth beatport          # sync from beatportdl credentials
ts-auth qobuz             # refresh Qobuz app credentials

# When Qobuz user session expires (no auto-refresh):
cd ~/Projects/tagslut && poetry run python -m tagslut auth login qobuz --email EMAIL --force
```

**DJ pool:**
- `--dj` flag writes two M3U files: one per-batch in the album folder, one at
  `MP3_LIBRARY/dj_pool.m3u` (accumulates over time)
- Import `dj_pool.m3u` into Rekordbox. Build crates there.
- No `DJ_LIBRARY` folder. No XML emit. No backfill.

**DB query:**
```bash
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*), SUM(CASE WHEN canonical_genre IS NOT NULL THEN 1 ELSE 0 END) FROM track_identity;"
```

Move the old 4-stage pipeline commands to a section:
```
## Legacy reference (RETIRED — 4-stage DJ pipeline)
# These commands still work but the workflow is no longer the primary model.
# Kept for reference only.
```

### 3. `docs/DOWNLOAD_STRATEGY.md`

Fix the incorrect statement: "beatportdl is permanently retired."

Replace with:
```
## beatportdl

beatportdl is the download tool for Beatport-only tracks. It is not retired.
Use `ts-get <beatport_url>` to route Beatport URLs through beatportdl automatically.
beatportdl's credentials file is at `~/Projects/beatportdl/beatportdl-credentials.json`
and is synced into tagslut's `tokens.json` by `ts-auth beatport`.

The prior note about beatportdl being "permanently retired" applied only to the
automatic TIDAL→Beatport fallback within tools/get-intake. beatportdl as an explicit
acquisition tool remains active.
```

Also update the providers.toml reference block — Qobuz is now active (not a scaffold):

```toml
[providers.qobuz]
metadata_enabled = true
download_enabled = false
trust = "secondary"
```

### 4. Move Technical Whitepaper files from repo root to `docs/reference/`

The following files are loose in the repo root and should be moved to `docs/reference/`:
- `Technical Whitepaper Building a Personal Beatport Metadata Tagger Using the Unofficial v4 API.md`
- `Technical Whitepaper Personal Qobuz Metadata Tagger.md`
- `Technical Whitepaper Personal TIDAL Metadata Tagger.md`

Use `git mv` for each:
```bash
git mv "Technical Whitepaper Building a Personal Beatport Metadata Tagger Using the Unofficial v4 API.md" docs/reference/
git mv "Technical Whitepaper Personal Qobuz Metadata Tagger.md" docs/reference/
git mv "Technical Whitepaper Personal TIDAL Metadata Tagger.md" docs/reference/
```

### 5. `.github/prompts/` — archive completed prompts

Move the following completed prompts to `.github/prompts/archive/` (create the directory):
```
dj-pool-m3u.prompt.md
enrich-hoarding-report.prompt.md
qobuz-metadata-provider.prompt.md
qobuz-auto-auth-prompt.prompt.md
pipeline-output-ux.prompt.md
tidal-auth-unification.prompt.md
get-no-download-pre-scan.prompt.md
today-fixes.prompt.md
tiddl-token-bridge.prompt.md
dj-pipeline-hardening.prompt.md
dj-workflow-audit.prompt.md
dj-ffmpeg-validation.prompt.md
dj-validation-gate-hardening.prompt.md
dj-validation-state-column-fix.prompt.md
dj-validate-and-emit-repair.prompt.md
dj-validate-gate.prompt.md
dj-mp3-reconcile-repair.prompt.md
dj-backfill-repair.prompt.md
unicode-path-normalization.prompt.md
resume-refresh-fix.prompt.md
fix-precheck-v3-schema.prompt.md
fix-get-forward-args.prompt.md
fix-backfill-conflicts-fixture.prompt.md
retire-beatport-download.prompt.md
bpdl-cover-fix.prompt.md
cli-verbose-progress.prompt.md
credential-consolidation-phase1.prompt.md
migration-0007-rename.prompt.md
migration-0012-provenance.prompt.md
open-streams-post-0010.prompt.md
```

Keep active in `.github/prompts/` (do not move):
```
beatport-circuit-breaker.prompt.md   ← queued for Codex
lexicon-reconcile.prompt.md          ← future work
repo-cleanup-supplement.prompt.md    ← operator-only, not started
dj-pool-wizard-transcode.prompt.md   ← under evaluation
dj-missing-tests-week1.prompt.md     ← under evaluation
qobuz-routing-tools-get.prompt.md    ← under evaluation
reccobeats-provider-stub.prompt.md   ← future work
postman-api-optimize.prompt.md       ← future work
intake-pipeline-hardening.prompt.md  ← keep as reference
```

Use `git mv` for each archived prompt:
```bash
mkdir -p .github/prompts/archive
git mv .github/prompts/<filename> .github/prompts/archive/
```

### 6. `docs/SESSION_REPORT_2026-04-01.md` — add beatportdl note

Append a line to the Open Issues section:
```
### beatportdl rebuild pending
The beatportdl source was patched (`interactions.go`: exit on empty input) to fix
the interactive prompt loop after non-interactive use. The build requires taglib arm64
(`arch -arm64 brew install taglib` then rebuild). Until rebuilt, `ts-get <beatport_url>`
will complete the download but hang at the "Enter url" prompt — Ctrl+C to exit.
```

---

## Commit

```
git add -A
git commit -m "docs: sync ROADMAP, COMMAND_GUIDE, DOWNLOAD_STRATEGY to April 2026 state; archive completed prompts; move whitepapers to docs/reference"
```
