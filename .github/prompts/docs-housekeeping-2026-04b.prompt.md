# docs-housekeeping-2026-04b — Archive stale docs, update live docs

## Do not modify any Python source, tests, migrations, or tools/ scripts.
## Do not recreate existing files.
## Use `git mv` for all moves. Single commit at the end.

---

## Context

As of 2026-04-02 the architecture changed substantially:
- 4-stage DJ pipeline (backfill/validate/XML emit) is RETIRED
- DJ_LIBRARY as a distinct folder is RETIRED
- DJ pool is now an M3U file at MP3_LIBRARY/dj_pool.m3u
- beatportdl is RESTORED as explicit download path (not retired)
- Active commands are: ts-get, ts-enrich, ts-auth (shell shortcuts)
- Qobuz is active as third metadata provider
- ReccoBeats is active as fourth provider (audio features)
- register-mp3 and fix-mp3-tags-from-filenames are new exec modules (coming soon)

---

## Part 1 — Archive these files

Move each to `docs/archive/` using `git mv`:

```bash
git mv docs/ACTION_PLAN.md docs/archive/
git mv docs/BACKFILL_GUIDE.md docs/archive/
git mv docs/BEATPORT_API_STATUS.md docs/archive/
git mv docs/CLEANUP_MANIFEST.md docs/archive/
git mv docs/CREDENTIAL_MANAGEMENT_AUDIT.md docs/archive/
git mv docs/DJ_PIPELINE.md docs/archive/
git mv docs/DJ_REVIEW_APP.md docs/archive/
git mv docs/DJ_WORKFLOW.md docs/archive/
git mv docs/PHASE1_STATUS.md docs/archive/
git mv docs/PHASE5_LEGACY_DECOMMISSION.md docs/archive/
git mv docs/PROGRESS_REPORT.md docs/archive/
git mv docs/PROJECT.md docs/archive/
git mv docs/PROMPT_SUITE_COMPLETE.md docs/archive/
git mv docs/PROVENANCE_INTEGRATION.md docs/archive/
git mv docs/REDESIGN_TRACKER.md docs/archive/
git mv docs/TECHNICAL_STATE_2026-03-24.md docs/archive/
git mv docs/WORKPLAN_2026-04-01.md docs/archive/
git mv "docs/mp3-audit-20260401.md" docs/archive/
```

---

## Part 2 — Rewrite OPERATOR_QUICK_START.md

Replace the entire content with the current reality:

```markdown
# Operator Quick Start

## Daily Startup

```bash
cd /Users/georgeskhawam/Projects/tagslut
source START_HERE.sh
```

## Token refresh (run before any download or enrichment session)

```bash
ts-auth
```

If Qobuz session is expired (ts-auth will tell you):
```bash
poetry run python -m tagslut auth login qobuz --email YOUR_EMAIL --force
```

If Beatport token is expired, launch beatportdl once to refresh:
```bash
cd ~/Projects/beatportdl && ./beatportdl-darwin-arm64
# Ctrl+C after the "Enter url" prompt appears
cd ~/Projects/tagslut && ts-auth beatport
```

## Download

```bash
ts-get <url>           # TIDAL, Qobuz, or Beatport URL
ts-get <url> --dj      # download + add to DJ pool M3U
```

## Enrich metadata

```bash
ts-enrich              # BPM, key, genre, label for all unenriched tracks
```

## DJ pool — Rekordbox

- Import `$MP3_LIBRARY/dj_pool.m3u` into Rekordbox
- Build crates there
- Synchronize to USB before gig

## Database stats

```bash
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*) FROM files;"
sqlite3 "$TAGSLUT_DB" "SELECT COUNT(*), SUM(CASE WHEN canonical_genre IS NOT NULL THEN 1 ELSE 0 END) FROM track_identity;"
```
```

---

## Part 3 — Replace DJ_POOL.md entirely

The old content describes a retired 4-stage pipeline. Replace with:

```markdown
<!-- Status: Active. Updated 2026-04-02 to reflect M3U model. -->

# DJ Pool

## Current model

The DJ pool is a single M3U playlist file, not a separate folder.

**Location:** `$MP3_LIBRARY/dj_pool.m3u`

## How it works

- `ts-get <url> --dj` downloads tracks and appends their MP3 paths to two M3U files:
  - A per-batch M3U named after the playlist/album, in the album folder
  - The global accumulating `$MP3_LIBRARY/dj_pool.m3u`
- Import either M3U into Rekordbox
- Build crates in Rekordbox
- Synchronize to USB before gig

## Rekordbox workflow

1. Import `$MP3_LIBRARY/dj_pool.m3u` into Rekordbox
2. Rekordbox analyzes BPM/beatgrid/waveform (this is the real BPM source for DJ use)
3. Build crates manually
4. Synchronize to USB before gig

## What DJ_LIBRARY is

`/Volumes/MUSIC/DJ_LIBRARY` is a legacy folder containing MP3s accumulated
before the M3U model was adopted. It is not actively written to. Its contents
are being registered into the DB and will be enriched via `ts-enrich`.

## What is NOT the DJ pool

- The 4-stage pipeline (backfill/validate/XML emit) is retired
- `DJ_LIBRARY` as a destination folder is retired
- `tagslut dj pool-wizard` is a legacy command, not the active workflow
- Rekordbox XML emit is not the active workflow

## Related

- `docs/DOWNLOAD_STRATEGY.md` — source selection
- `docs/CREDENTIAL_MANAGEMENT.md` — token management
```

---

## Part 4 — Update WORKFLOWS.md

Replace the Status comment at the top and the entire "Primary URL Intake" and
"Legacy: tools/get Wrapper" sections with the current model.
Leave the V3 Migration Operations, Manual Phase Workflow, and Maintenance sections
in place but add a banner at the top marking them as legacy reference:

At the very top, replace the status comment with:

```markdown
<!-- Status: Partially active. Top-level workflow sections updated 2026-04-02.
     V3 migration, manual phase, and maintenance sections below are legacy reference
     kept for archaeology. Current daily workflow is in OPERATOR_QUICK_START.md. -->
```

Replace the "Primary URL Intake (Canonical)" section with:

```markdown
## Current Daily Workflow

```bash
# Download (TIDAL, Qobuz, or Beatport URL)
ts-get <url>
ts-get <url> --dj        # + DJ pool M3U

# Metadata enrichment
ts-enrich                # runs beatport → tidal → qobuz → reccobeats

# Token refresh
ts-auth                  # refresh all providers
ts-auth tidal            # one provider only
ts-auth beatport         # one provider only
ts-auth qobuz            # one provider only
```

See `docs/OPERATOR_QUICK_START.md` for full startup sequence.

---

## Legacy reference (pre-April 2026 pipeline)

The sections below describe the old `tagslut intake url` / `tools/get` pipeline
and 8-step manual workflow. They are kept for archaeology only.
```

---

## Part 5 — Update SCRIPT_SURFACE.md

Add `ts-get`, `ts-enrich`, `ts-auth`, `tools/auth`, `tools/enrich` to the
Operational Wrappers section. Add them after item 5 (`tools/tagslut`):

```markdown
6. `ts-get <url> [--dj] [--enrich]` (shell function in ~/.zshrc)
Role: Primary download entry point. Routes to tiddl (TIDAL), streamrip (Qobuz),
or beatportdl (Beatport) based on URL domain. `--dj` writes DJ pool M3U files.

7. `ts-enrich` (shell function in ~/.zshrc)
Role: Run metadata hoarding enrichment. Reads $TAGSLUT_DB, hits beatport →
tidal → qobuz → reccobeats, fills BPM/key/genre/label. Resumable.

8. `ts-auth [tidal|beatport|qobuz|all]` (shell function in ~/.zshrc)
Role: Refresh all provider tokens. Validates Qobuz session. Syncs beatportdl
credentials. Wraps `tools/auth`.

9. `tools/auth [tidal|beatport|qobuz|all]`
Role: Token refresh implementation. Called by ts-auth. Handles:
- TIDAL: delegates to `tiddl auth refresh`
- Beatport: attempts API refresh of stored token; syncs from beatportdl credentials
- Qobuz: refreshes app credentials from bundle.js; validates session; pushes to streamrip dev_config.toml

10. `tools/enrich`
Role: Zero-config enrichment wrapper. Reads $TAGSLUT_DB from environment.
Called by ts-enrich.
```

Also update the note on `tools/get` (item 1) to remove the description of
`--dj` as deprecated and update to reflect current routing:

Replace:
```
- `--dj` is deprecated legacy behavior. See `docs/DJ_PIPELINE.md` for the canonical 4-stage DJ pipeline.
```
With:
```
- `--dj` writes DJ pool M3U files (per-batch and global dj_pool.m3u at MP3_LIBRARY root).
```

---

## Part 6 — Update ARCHITECTURE.md status header

Replace the status comment at the top:

Old:
```
<!-- Status: Active document. Synced 2026-03-14 after migration 0010 (DJ pipeline tables). Historical or superseded material belongs in docs/archive/. -->
```

New:
```
<!-- Status: Active document. Last major sync 2026-03-14. Note: sections describing
     the 4-stage DJ pipeline (backfill/validate/XML) and DJ_LIBRARY as a distinct
     folder reflect the pre-April 2026 architecture. Current model uses M3U-based
     DJ pool. See docs/DJ_POOL.md and docs/OPERATOR_QUICK_START.md for current state. -->
```

---

## Commit

```bash
git add -A
git commit -m "docs: archive 18 stale docs, rewrite OPERATOR_QUICK_START and DJ_POOL, update WORKFLOWS/SCRIPT_SURFACE/ARCHITECTURE to April 2026 state"
```
