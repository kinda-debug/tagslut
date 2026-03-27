# tagslut — Project Directives (REVISED 2026-03-26)

These directives apply to every agent working in this repo.
They supplement AGENT.md and CLAUDE.md. When in conflict,
these directives take precedence.

Last updated: 2026-03-26

---

## Identity and origin

Repository: <https://github.com/kinda-debug/tagslut>
Active branch: dev
Owner account: kinda-debug (GitHub), georgeskhawam (personal)
Prior org: tagslut (GitHub) — treat all references to tagslut/tagslut as
pointing to kinda-debug/tagslut. They are the same repo.

---

## DB state

There are two DB contexts. Never confuse them.

LEGACY (read-only archaeology):
  /Users/georgeskhawam/Projects/tagslut_db/LEGACY_2026-03-04_PICARD/music_v3.db
  Contaminated by MusicBrainz Picard tags. Do not write to it.
  Do not use as $TAGSLUT_DB default.

FRESH (target for all new work):
  /Users/georgeskhawam/Projects/tagslut_db/FRESH_2026/music_v3.db
  Does not exist yet. Must be initialized from migrations.
  All clean-slate ingestion goes here.

$TAGSLUT_DB must point at FRESH once initialized.
Until then, any test that requires a DB must use a temp/fixture DB.

---

## Volume layout (current machine)

/Volumes/MUSIC/MASTER_LIBRARY    FLAC master library — source of truth for audio
/Volumes/MUSIC/MP3_LIBRARY       MP3 copies for playback (full metadata + lyrics)
/Volumes/MUSIC/DJ_LIBRARY        DJ-admitted MP3s (admission-gated subset)
/Volumes/MUSIC/DJ_POOL_MANUAL_MP3  Manual DJ pool additions
/Volumes/MUSIC/mdl               Staging root for downloads
/Volumes/MUSIC/lexicondj.db      Lexicon DJ database (read-only reference)
/Volumes/SAD/                    Legacy epoch DBs — read-only, no writes

$MASTER_LIBRARY = /Volumes/MUSIC/MASTER_LIBRARY
$MP3_LIBRARY    = /Volumes/MUSIC/MP3_LIBRARY
$DJ_LIBRARY     = /Volumes/MUSIC/DJ_LIBRARY
$DJ_MP3_ROOT    = /Volumes/MUSIC/DJ_LIBRARY
$STAGING_ROOT   = /Volumes/MUSIC/mdl

If a volume is not mounted, operations that require it must fail
with a clear error — do not silently fall back to local paths.

---

## Primary user workflows

These are the ONLY flags most operators will ever use. Both are stable and primary.

### tagslut --dj [OPTIONS]

Intake a DJ track or playlist from Beatport/TIDAL and add to DJ_LIBRARY.

**What it does:**
- Fetches metadata from multiple providers (Beatport, TIDAL, Qobuz, Discogs)
- Verifies audio integrity against expected duration
- Stamps with ingestion provenance (verified/high/uncertain)
- Writes MP3 copy to $DJ_LIBRARY with full metadata and lyrics
- Returns track identity and dedupe status

**Options:**
```
  --url URL              Beatport or TIDAL URL (required)
  --force-download       Skip truncation check, download anyway
  --refresh              Re-harvest metadata, ignore cache
  --dry-run              Show what would happen, don't write
```

**Example:**
```
tagslut --dj --url https://www.beatport.com/track/example/12345678
tagslut --dj --url https://tidal.com/browse/track/123456789 --force-download
```

### tagslut --mp3 [OPTIONS]

Build MP3 copies from FLAC master library into MP3_LIBRARY.

**What it does:**
- Transcodes FLAC → MP3 @ 320kbps
- Embeds all metadata: ISRC, artist, album, year, lyrics
- Builds dedupe index
- Skips files already present (unless --refresh)
- Syncs deletions from MASTER_LIBRARY to MP3_LIBRARY

**Options:**
```
  --refresh              Rebuild all MP3s, re-harvest metadata
  --dry-run              Show what would be built
  --batch SIZE           Process N files per run (default: 100)
  --force                Skip integrity checks, transcode anyway
```

**Example:**
```
tagslut --mp3                    # Build missing MP3s
tagslut --mp3 --refresh          # Rebuild all with fresh metadata
tagslut --mp3 --batch 50 --dryrun # Show next 50 files to process
```

---

## Implementation detail (do not expose to users)

These two user-facing flags invoke a 4-stage pipeline internally:
  intake → metadata-harvest → verify-integrity → write-output

Users don't call the stages directly. They call `--dj` or `--mp3`.

If you need to debug a specific stage, use:
```
tagslut intake --url <url> --dry-run        # Stage 1: ingest only
tagslut metadata-harvest --refresh          # Stage 2: API calls only
tagslut verify-integrity --file <path>      # Stage 3: duration checks
```

But these are NOT for daily use — they exist for debugging and operator runbooks.

---

## Provenance is non-negotiable

Every track_identity row must have four fields set at insert time:
  ingested_at         ISO 8601 UTC, set once, never updated
  ingestion_method    controlled vocabulary (see INGESTION_PROVENANCE.md)
  ingestion_source    specific evidence string
  ingestion_confidence  verified | high | uncertain | legacy

These are NOT NULL. Any migration or insert that omits them is wrong.
Full spec: docs/INGESTION_PROVENANCE.md

---

## The Picard rule

MusicBrainz Picard must never touch files under $MASTER_LIBRARY.
Any identity derived from Picard-written tags gets:
  ingestion_method = 'picard_tag'
  ingestion_confidence = 'legacy'
and is excluded from DJ export and canonical writeback until
manually reviewed and upgraded.

---

## Tool assignment

Codex:   autonomous implementation — all tasks with a prompt file
         in .github/prompts/. Run from repo root.
         Never ask Codex to design — give it a spec first.

Claude Code (rate-limited — use sparingly):
         judgment-critical work: prompt authoring, architecture
         decisions, cross-cutting audit, debugging where the
         problem itself is unclear.

Copilot+: editor inline completions and single-file chat only.
          Not for agentic tasks.

---

## What Codex must not do without explicit instruction

- Touch tagslut/storage/v3/schema.py without a migration file
- Modify any DB file directly (use migrations only)
- Write to $MASTER_LIBRARY, $DJ_LIBRARY, $MP3_LIBRARY, or any volume
- Change the interface of tools/get or tools/get-intake
  without updating the corresponding CLI help text
- Add new Python dependencies without updating pyproject.toml
  and confirming with the operator
- Run the full test suite — use targeted pytest only

---

## Active task priority order

1. resume-refresh-fix (tools/get-intake) — unblocks daily intake
2. ingestion provenance migration — prerequisite for fresh DB
3. fresh DB initialization — prerequisite for clean-slate ingestion
4. repo cleanup — parallel, no dependencies
5. Phase 1 PR chain (PRs 9-11) — blocked on migration 0006 merge
6. DJ pipeline hardening — after Phase 1

Do not skip ahead. Do not work on item 5 before items 1-2 are done.

---

## Commit conventions

Format: type(scope): description
Types: fix, feat, chore, docs, test, refactor
Scope: the primary file or module changed
Examples:
  fix(intake): suppress dest_exists discard plan in resume mode
  feat(schema): add ingestion provenance columns to track_identity
  chore(cleanup): archive dead scripts and stale docs
  docs(roadmap): update with cleanup progress

One logical change per commit. Do not bundle unrelated changes.
Commit after each completed step, not at end of session.

---

## Testing policy (clarification)

Default: targeted pytest only.
  `poetry run pytest tests/<specific_module> -v`

Full suite (`poetry run pytest tests/ -x -q`) is permitted ONLY as a final
gate immediately before merging a PR. Never during implementation.
This exception must be stated explicitly in the task — if a prompt does not
say "run the full suite as a final gate", targeted only applies.

---

## Force-push prohibition

`git push --force` and `git filter-repo` are operator-only maintenance
procedures. They must never appear in a Codex prompt or be executed by
any agent. The git history cleanup task lives in `docs/OPS_RUNBOOK.md`
and is executed manually by the operator only.

---

## Confidence tier model (5-tier)

The correct model is five tiers, not four:

  verified        Two+ providers confirmed same ISRC at ingest time (active check)
  corroborated    Multiple stored provider IDs present, all agree on ISRC
  high            Single provider API match, confirmed provider ID
  uncertain       Fuzzy match, fingerprint below 0.90, text-only, or any conflict
  legacy          Picard tag, unknown origin, or unverified migration

Full multi-provider policy: `docs/MULTI_PROVIDER_ID_POLICY.md`

---

## Two ingestion tracks

### Track A: Clean-slate (new files via --dj)
Files from Beatport/TIDAL via `tagslut --dj --url ...`
- ingestion_method = 'provider_api'
- ingestion_confidence = 'verified' (both providers agree) or 'high' (one provider)

### Track B: Legacy (older files with cross-provider IDs)
Existing files with accumulated metadata from multiple sources
- ingestion_method = 'multi_provider_reconcile'
- ingestion_confidence = 'corroborated' (all IDs agree on ISRC), 'uncertain' (conflict)
- Conflicts preserved in canonical_payload_json.provider_id_conflicts — never dropped

---

## Provider ID policy

All provider IDs preserved if they do not conflict with the ISRC.
Agreement across providers = positive confirmation.
Conflict = provenance failure — flagged not silently resolved.
Full policy: `docs/MULTI_PROVIDER_ID_POLICY.md`
